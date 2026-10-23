package dev.openguard.scan;

import static org.junit.jupiter.api.Assertions.*;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class DeliveryCoreTest {
    @TempDir Path root;

    @Test void cli_refuses_existing_or_nested_output_and_preserves_input() throws Exception {
        Path checkout = Files.createDirectory(root.resolve("input"));
        Files.writeString(checkout.resolve("requirements.txt"), "requests==2.32.3");
        Path existing = Files.createDirectory(root.resolve("old-report"));
        Files.writeString(existing.resolve("report.html"), "old immutable report");
        assertThrows(IllegalArgumentException.class, () -> RealRepositoryScan.main(new String[]{"--trusted-checkout", checkout.toString(), "self-authored", existing.toString()}));
        assertThrows(IllegalArgumentException.class, () -> RealRepositoryScan.main(new String[]{"--trusted-checkout", checkout.toString(), "self-authored", checkout.resolve("out").toString()}));
        assertEquals("old immutable report", Files.readString(existing.resolve("report.html")));
    }

    @Test void ranges_are_not_exact_versions() throws Exception {
        Files.writeString(root.resolve("requirements.txt"), "requests>=2.32.3\nflask==3.1.0\n");
        var result = new RepositoryScanner().scanTrustedCheckout(root, "self-authored", "before");
        assertEquals("unknown", result.components().getFirst().version());
        assertEquals("3.1.0", result.components().get(1).version());
    }

    @Test void a_generic_gpl_heading_does_not_invent_a_version_or_later_grant() throws Exception {
        Files.writeString(root.resolve("LICENSE"), "GNU GENERAL PUBLIC LICENSE\nVersion 2, June 1991");
        var result = new RepositoryScanner().scanTrustedCheckout(root, "self-authored-test", "before");
        assertEquals("NOASSERTION", result.licenses().getFirst().spdxId());
        assertEquals("pending", result.licenses().getFirst().verificationStatus());
    }

    @Test void unreadable_manifest_remains_partial_and_visible_in_the_report() throws Exception {
        Files.writeString(root.resolve("package.json"), "{invalid-json");
        var result = new RepositoryScanner().scanTrustedCheckout(root, "self-authored-test", "before");
        assertEquals("partial", result.status());
        assertTrue(StructuredReports.html(result).contains("package_manifest_unreadable:package.json"));
    }

    @Test void all_profiles_are_rendered_and_target_code_is_never_executed() throws Exception {
        Files.createDirectories(root.resolve("huggingface/models"));
        for (String name : java.util.List.of("one", "two")) {
            Files.writeString(root.resolve("huggingface/models/" + name + ".json"),
                "{\"id\":\"org/" + name + "\",\"gated\":false,\"cardData\":{\"license\":\"mit\"}}");
        }
        Files.writeString(root.resolve("trap.py"), "raise RuntimeError('must not execute')");
        var result = new RepositoryScanner().scanTrustedCheckout(root, "self-authored-test", "after");
        assertEquals(2, result.resourceProfiles().size());
        assertTrue(StructuredReports.html(result).contains("org/one"));
        assertTrue(StructuredReports.html(result).contains("org/two"));
    }
}
