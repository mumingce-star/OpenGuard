package dev.openguard.bench;

import com.fasterxml.jackson.databind.JsonNode;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.regex.Pattern;

final class ArtifactIntegrityValidator {
  static final long MAX_ARTIFACT_BYTES = 64L * 1024L * 1024L;
  private static final Pattern DRIVE = Pattern.compile("^[A-Za-z]:.*");
  private static final Pattern URI = Pattern.compile("^[A-Za-z][A-Za-z0-9+.-]*:.*");

  List<Diagnostic> validate(Path manifestPath, JsonNode artifacts) {
    List<Diagnostic> diagnostics = new ArrayList<>();
    Path root = manifestPath.toAbsolutePath().normalize().getParent();
    for (int i = 0; i < artifacts.size(); i++) {
      JsonNode artifact = artifacts.get(i);
      String pointer = "/artifacts/" + i;
      String pathText = artifact.path("path").asText();
      Path file = resolveSafe(root, pathText, pointer, diagnostics);
      if (file == null) continue;

      boolean referenceOnly = "reference_only".equals(artifact.path("redistribution").asText());
      if (!Files.exists(file, LinkOption.NOFOLLOW_LINKS) && referenceOnly) continue;
      if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)) {
        diagnostics.add(error(
            "BENCH_ARTIFACT_NOT_REGULAR_FILE", pointer + "/path",
            "Artifact must be a regular local file."));
        continue;
      }

      try {
        long actualSize = Files.size(file);
        long declaredSize = artifact.path("size_bytes").asLong();
        if (actualSize > MAX_ARTIFACT_BYTES) {
          diagnostics.add(error(
              "BENCH_ARTIFACT_TOO_LARGE", pointer + "/size_bytes",
              "Artifact exceeds the configured size limit."));
          continue;
        }
        if (actualSize != declaredSize) {
          diagnostics.add(error(
              "BENCH_ARTIFACT_SIZE_MISMATCH", pointer + "/size_bytes",
              "Artifact byte size does not match the manifest."));
        }
        String actualHash = sha256(file);
        if (!actualHash.equals(artifact.path("sha256").asText())) {
          diagnostics.add(error(
              "BENCH_ARTIFACT_HASH_MISMATCH", pointer + "/sha256",
              "Artifact SHA-256 does not match the manifest."));
        }
      } catch (IOException exception) {
        diagnostics.add(error(
            "BENCH_ARTIFACT_READ_FAILED", pointer + "/path",
            "Artifact could not be read safely."));
      }
    }
    return diagnostics;
  }

  Path resolveSafe(Path root, String pathText, String pointer, List<Diagnostic> diagnostics) {
    if (!isCanonicalRelativePath(pathText)) {
      diagnostics.add(error(
          "BENCH_ARTIFACT_PATH_UNSAFE", pointer + "/path",
          "Artifact path must be a canonical repository-relative path."));
      return null;
    }
    Path relative;
    try {
      relative = Path.of(pathText);
    } catch (RuntimeException exception) {
      diagnostics.add(error(
          "BENCH_ARTIFACT_PATH_UNSAFE", pointer + "/path",
          "Artifact path must be a canonical repository-relative path."));
      return null;
    }
    Path candidate = root.resolve(relative).normalize();
    if (!candidate.startsWith(root)) {
      diagnostics.add(error(
          "BENCH_ARTIFACT_PATH_ESCAPE", pointer + "/path",
          "Artifact path escapes the manifest directory."));
      return null;
    }

    Path current = root;
    for (Path segment : root.relativize(candidate)) {
      current = current.resolve(segment);
      if (Files.isSymbolicLink(current)) {
        diagnostics.add(error(
            "BENCH_ARTIFACT_SYMLINK", pointer + "/path",
            "Artifact paths must not contain symbolic links."));
        return null;
      }
    }
    return candidate;
  }

  static boolean isCanonicalRelativePath(String value) {
    if (value == null || value.isBlank() || value.length() > 1024) return false;
    if (value.indexOf('\0') >= 0 || value.indexOf('\\') >= 0
        || value.indexOf('?') >= 0 || value.indexOf('#') >= 0) return false;
    if (value.startsWith("/") || value.startsWith("\\") || DRIVE.matcher(value).matches()
        || URI.matcher(value).matches() || value.contains("//")) return false;
    String[] segments = value.split("/", -1);
    for (String segment : segments) {
      if (segment.isEmpty() || ".".equals(segment) || "..".equals(segment)) return false;
    }
    return true;
  }

  static String sha256(Path path) throws IOException {
    try {
      MessageDigest digest = MessageDigest.getInstance("SHA-256");
      try (InputStream input = Files.newInputStream(path)) {
        byte[] buffer = new byte[8192];
        int read;
        while ((read = input.read(buffer)) != -1) digest.update(buffer, 0, read);
      }
      return HexFormat.of().formatHex(digest.digest());
    } catch (NoSuchAlgorithmException impossible) {
      throw new IllegalStateException("SHA-256 is unavailable", impossible);
    }
  }

  private static Diagnostic error(String code, String pointer, String message) {
    return new Diagnostic(code, "error", pointer, message);
  }
}
