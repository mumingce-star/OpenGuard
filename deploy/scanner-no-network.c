#define _GNU_SOURCE
/* OpenGuard's build-host-native launcher; no third-party implementation copied. */
#include <errno.h>
#include <fcntl.h>
#include <linux/landlock.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <linux/audit.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <stddef.h>
#include <stdio.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <unistd.h>

/* ABI v3 rights are stable even when the build headers predate Linux 6.2.
 * Runtime ABI >= 3 is mandatory; never silently omit truncate protection. */
#ifndef LANDLOCK_ACCESS_FS_TRUNCATE
#define LANDLOCK_ACCESS_FS_TRUNCATE (1ULL << 14)
#endif

#if defined(__aarch64__)
#define NATIVE_ARCH AUDIT_ARCH_AARCH64
#elif defined(__x86_64__)
#define NATIVE_ARCH AUDIT_ARCH_X86_64
#else
#error Unsupported build-host architecture
#endif

static int allow_path(int ruleset, const char *path, unsigned long long rights, int optional) {
    int fd = open(path, O_PATH | O_CLOEXEC);
    if (fd < 0) return optional && errno == ENOENT ? 0 : -1;
    struct stat info;
    if (fstat(fd, &info)) { close(fd); return -1; }
    if (!S_ISDIR(info.st_mode)) rights &= ~(LANDLOCK_ACCESS_FS_READ_DIR);
    struct landlock_path_beneath_attr rule = {.allowed_access = rights, .parent_fd = fd};
    int result = syscall(__NR_landlock_add_rule, ruleset, LANDLOCK_RULE_PATH_BENEATH, &rule, 0);
    close(fd);
    return result;
}

static int restrict_files(const char *temp, const char *task) {
    const unsigned long long read = LANDLOCK_ACCESS_FS_READ_FILE | LANDLOCK_ACCESS_FS_READ_DIR;
    const unsigned long long run = read | LANDLOCK_ACCESS_FS_EXECUTE;
    const unsigned long long write = read | LANDLOCK_ACCESS_FS_WRITE_FILE |
        LANDLOCK_ACCESS_FS_REMOVE_DIR | LANDLOCK_ACCESS_FS_REMOVE_FILE |
        LANDLOCK_ACCESS_FS_MAKE_DIR | LANDLOCK_ACCESS_FS_MAKE_REG |
        LANDLOCK_ACCESS_FS_MAKE_SOCK | LANDLOCK_ACCESS_FS_MAKE_FIFO |
        LANDLOCK_ACCESS_FS_MAKE_SYM | LANDLOCK_ACCESS_FS_REFER | LANDLOCK_ACCESS_FS_TRUNCATE;
    if (syscall(__NR_landlock_create_ruleset, NULL, 0, LANDLOCK_CREATE_RULESET_VERSION) < 3) return -1;
    struct landlock_ruleset_attr attr = {.handled_access_fs = (1ULL << 15) - 1};
    int ruleset = syscall(__NR_landlock_create_ruleset, &attr, sizeof(attr), 0);
    if (ruleset < 0) return -1;
    const char *runtime[] = {"/usr", "/lib", "/lib64", "/bin", "/sbin",
        "/opt/openguard/scanner-no-network", "/opt/scancode", "/opt/syft", "/opt/api", "/run/rosetta", NULL};
    const char *config[] = {"/etc/ld.so.cache", "/etc/ld.so.conf", "/etc/ld.so.conf.d",
        "/etc/passwd", "/etc/group", "/etc/localtime", "/etc/os-release", "/etc/mime.types",
        "/proc/cpuinfo", "/proc/meminfo", "/proc/stat", "/proc/filesystems",
        "/proc/sys/vm/mmap_min_addr", "/proc/sys/kernel/osrelease", "/proc/self/status", "/proc/self/maps", "/proc/self/mountinfo", "/proc/self/mounts", NULL};
    int result = -1;
    /* binfmt interpreters may live outside the visible root mount. Grant only
     * the trusted parent executable inode, never its proc directory or memory. */
    char parent_exe[64];
    snprintf(parent_exe, sizeof(parent_exe), "/proc/%ld/exe", (long)getppid());
    if (allow_path(ruleset, parent_exe, run, 0)) goto out;
    for (int i = 0; runtime[i]; i++) if (allow_path(ruleset, runtime[i], run, 1)) goto out;
    for (int i = 0; config[i]; i++) if (allow_path(ruleset, config[i], read, 1)) goto out;
    if (allow_path(ruleset, "/proc/self/fd", LANDLOCK_ACCESS_FS_READ_DIR, 0) ||
        allow_path(ruleset, "/dev/null", LANDLOCK_ACCESS_FS_READ_FILE | LANDLOCK_ACCESS_FS_WRITE_FILE, 0) ||
        allow_path(ruleset, "/dev/urandom", LANDLOCK_ACCESS_FS_READ_FILE, 0) ||
        allow_path(ruleset, "/dev/random", LANDLOCK_ACCESS_FS_READ_FILE, 0) ||
        allow_path(ruleset, temp, write, 0)) goto out;
    if (strcmp(task, "-") && allow_path(ruleset, task, read, 0)) goto out;
    result = syscall(__NR_landlock_restrict_self, ruleset, 0);
out:
    close(ruleset);
    return result;
}

int main(int argc, char **argv) {
    if (argc < 5 || strcmp(argv[1], "--files")) return 125;
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) || restrict_files(argv[2], argv[3])) {
        fputs("scanner filesystem sandbox unavailable\n", stderr);
        return 125;
    }
    struct sock_filter rules[] = {
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, arch)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, NATIVE_ARCH, 1, 0),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),
#if defined(__x86_64__)
        /* x32 shares the audit arch but has a distinct syscall-number ABI. */
        BPF_JUMP(BPF_JMP | BPF_JSET | BPF_K, 0x40000000, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),
#endif
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_io_uring_setup, 5, 0),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_socket, 1, 0),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_socketpair, 0, 4),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, args[0])),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, AF_UNIX, 2, 0),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | EPERM),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
    };
    struct sock_fprog program = { .len = sizeof(rules) / sizeof(rules[0]), .filter = rules };
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) ||
        prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program)) {
        fputs("scanner network sandbox unavailable\n", stderr);
        return 125;
    }
    execvp(argv[4], &argv[4]);
    fputs("scanner executable unavailable\n", stderr);
    return 126;
}
