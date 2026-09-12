package dev.openguard.scan;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

class RepositoryScannerTest {
    @Test
    void scans_manifests_license_and_ai_reference_without_executing_target_code() throws Exception {
        Path fixture = Path.of("target", "scanner-contract-fixture").toAbsolutePath();
        Files.createDirectories(fixture);
        try {
            Files.writeString(fixture.resolve("pyproject.toml"), "[project]\ndependencies = [\"flask>=3.0\"]\n");
            Files.writeString(fixture.resolve("package.json"), "{\"dependencies\":{\"react\":\"18.3.1\"}}");
            Files.writeString(fixture.resolve("LICENSE"), "MIT License\nPermission is hereby granted");
            Files.writeString(fixture.resolve("model.md"), "model=https://huggingface.co/org/model");

            ScanResult result = new RepositoryScanner().scanTrustedCheckout(fixture, "fixture", "fixture-revision");

            assertEquals("completed", result.status());
            assertEquals(2, result.components().size());
            assertEquals("MIT", result.licenses().getFirst().spdxId());
            assertEquals(1, result.aiAssets().size());
            assertTrue(result.findings().stream().allMatch(finding -> "review_required".equals(finding.outcome())));
            assertTrue(StructuredReports.json(result).contains("scan_id"));
            assertTrue(StructuredReports.html(result).contains("OpenGuard scan report"));
        } finally {
            try (var paths = Files.walk(fixture)) {
                paths.sorted(java.util.Comparator.reverseOrder()).forEach(path -> {
                    try { Files.deleteIfExists(path); } catch (Exception ignored) { }
                });
            }
        }
    }
}
