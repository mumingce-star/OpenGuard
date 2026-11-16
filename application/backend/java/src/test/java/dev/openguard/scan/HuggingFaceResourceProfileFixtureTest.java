package dev.openguard.scan;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import org.junit.jupiter.api.Test;

/** Guards the public, minimal HF observation corpus without contacting any provider. */
class HuggingFaceResourceProfileFixtureTest {
    private static final ObjectMapper JSON = new ObjectMapper();

    @Test
    void fixed_real_snapshots_have_traceable_observations_and_no_license_or_authorization_upgrade() throws Exception {
        Path root = fixtureRoot();
        JsonNode manifest = JSON.readTree(root.resolve("manifest.json").toFile());
        assertEquals("openguard.resource-profile-fixture-manifest/1", manifest.path("schema").asText());
        assertEquals(10, manifest.withArray("records").size());
        assertEquals(5L, manifest.withArray("records").findValuesAsText("resource_kind").stream().filter("model"::equals).count());
        assertEquals(5L, manifest.withArray("records").findValuesAsText("resource_kind").stream().filter("dataset"::equals).count());

        for (JsonNode record : manifest.withArray("records")) {
            JsonNode snapshot = readAndVerify(root, record);
            assertEquals("huggingface", record.path("observed").path("provider").asText());
            assertEquals("pending", record.path("authorization_status").asText());
            assertTrue(record.path("license_expression_id").isNull());
            for (String field : new String[] {"canonical_id", "revision", "provider", "visibility", "gated", "disabled", "declared_license_raw"}) {
                JsonNode pointer = record.path("field_evidence").path(field);
                assertTrue(pointer.isTextual(), record.path("case_id").asText() + " missing evidence for " + field);
                assertFalse(snapshot.at(pointer.asText()).isMissingNode(), record.path("case_id").asText() + " pointer: " + pointer.asText());
            }
        }
    }

    @Test
    void synthetic_counterexamples_are_explicit_and_fail_closed() throws Exception {
        Path root = fixtureRoot();
        JsonNode manifest = JSON.readTree(root.resolve("manifest.json").toFile());
        assertEquals(3, manifest.withArray("counterexamples").size());
        for (JsonNode example : manifest.withArray("counterexamples")) {
            readAndVerify(root, example);
            assertEquals("synthetic_negative_case", example.path("source_kind").asText());
            assertEquals("pending", example.path("expected").path("authorization_status").asText());
            assertTrue(example.path("expected").path("license_expression_id").isNull());
        }
        JsonNode noAssertion = manifest.withArray("counterexamples").get(2);
        assertEquals("NOASSERTION", noAssertion.path("expected").path("declared_license_raw").asText());
        assertNull(noAssertion.path("expected").path("license_expression_id").textValue());
    }

    private JsonNode readAndVerify(Path root, JsonNode entry) throws Exception {
        Path fixture = root.resolve(entry.path("fixture").asText()).normalize();
        assertTrue(fixture.startsWith(root) && Files.isRegularFile(fixture));
        assertEquals(entry.path("source_file_sha256").asText(), sha256(Files.readAllBytes(fixture)));
        return JSON.readTree(fixture.toFile());
    }

    private Path fixtureRoot() {
        Path cursor = Path.of(System.getProperty("user.dir")).toAbsolutePath().normalize();
        while (cursor != null) {
            Path candidate = cursor.resolve("tests/fixtures/huggingface/resource-profile-v1");
            if (Files.isDirectory(candidate)) return candidate;
            cursor = cursor.getParent();
        }
        throw new IllegalStateException("Hugging Face resource-profile fixture directory was not found.");
    }

    private String sha256(byte[] data) throws Exception {
        byte[] hash = MessageDigest.getInstance("SHA-256").digest(data);
        StringBuilder value = new StringBuilder(64);
        for (byte b : hash) value.append(String.format("%02x", b));
        return value.toString();
    }
}
