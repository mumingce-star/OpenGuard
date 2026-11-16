package dev.openguard.bench;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

class BenchManifestCliProcessTest {
  @Test
  void directJavaProcessPreservesPolicyExitCodeThree() throws Exception {
    Path example = examplesRoot().resolve("invalid/holdout-exposure.json");
    String executable = System.getProperty("os.name").startsWith("Windows") ? "java.exe" : "java";
    String classPath = System.getProperty("surefire.test.class.path", System.getProperty("java.class.path"));
    Process process =
        new ProcessBuilder(
                Path.of(System.getProperty("java.home"), "bin", executable).toString(),
                "-cp",
                classPath,
                BenchManifestCli.class.getName(),
                "validate",
                example.toString())
            .start();

    String stdout = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
    String stderr = new String(process.getErrorStream().readAllBytes(), StandardCharsets.UTF_8);
    int exit = process.waitFor();

    assertEquals(3, exit);
    assertEquals("", stderr);
    JsonNode report = new ObjectMapper().readTree(stdout);
    assertTrue(report.path("valid").asBoolean());
    assertTrue(
        report.path("diagnostics").findValuesAsText("code").contains("BENCH_TIER_NOT_MET"));
  }

  private Path examplesRoot() {
    Path cursor = Path.of(System.getProperty("user.dir")).toAbsolutePath().normalize();
    while (cursor != null) {
      Path candidate = cursor.resolve("benchmarks/examples/v2");
      if (Files.isDirectory(candidate)) return candidate;
      cursor = cursor.getParent();
    }
    throw new IllegalStateException("Bench example directory was not found.");
  }
}
