package dev.openguard.bench;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import org.junit.jupiter.api.Test;

class BenchExamplesTest {
  private final BenchManifestService service = new BenchManifestService();

  @Test
  void allPublishedPositiveExamplesPass() {
    Path valid = examplesRoot().resolve("valid");
    for (String name :
        new String[] {
          "smoke.json",
          "development.json",
          "reportable-single-human.json",
          "reportable-independent.json"
        }) {
      ValidationOutcome outcome = service.validate(valid.resolve(name));
      assertEquals(0, outcome.exitCode(), name + ": " + outcome.report().diagnostics());
    }
  }

  @Test
  void allPublishedNegativeExamplesFailWithExpectedDiagnostic() {
    Path invalid = examplesRoot().resolve("invalid");
    Map<String, Expected> examples =
        Map.of(
            "unknown-field.json", new Expected(1, "BENCH_SCHEMA_ADDITIONALPROPERTIES"),
            "unsafe-path.json", new Expected(1, "BENCH_ARTIFACT_PATH_UNSAFE"),
            "dangling-reference.json", new Expected(1, "BENCH_ARTIFACT_REFERENCE_MISSING"),
            "split-leakage.json", new Expected(1, "BENCH_SPLIT_FAMILY_LEAKAGE"),
            "hash-mismatch.json", new Expected(1, "BENCH_ARTIFACT_HASH_MISMATCH"),
            "holdout-exposure.json", new Expected(3, "BENCH_HOLDOUT_EXPOSED"),
            "revision-parent.json", new Expected(1, "BENCH_SCHEMA_TYPE"));

    examples.forEach(
        (name, expected) -> {
          ValidationOutcome outcome = service.validate(invalid.resolve(name));
          assertEquals(expected.exitCode(), outcome.exitCode(), name);
          assertTrue(
              outcome.report().diagnostics().stream()
                  .anyMatch(d -> d.code().equals(expected.code())),
              name + ": " + outcome.report().diagnostics());
        });
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

  private record Expected(int exitCode, String code) {}
}
