package dev.openguard.scan;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Instant;
import org.junit.jupiter.api.Test;

/** Offline-only v2 corpus gate; it never contacts a Hugging Face endpoint. */
class HuggingFaceResourceProfileV2FixtureTest {
    private static final ObjectMapper JSON = new ObjectMapper();

    @Test
    void five_models_and_five_datasets_have_double_hashes_and_stay_pending() throws Exception {
        Path root = fixtureRoot();
        JsonNode manifest = JSON.readTree(root.resolve("manifest.json").toFile());

        assertEquals("openguard.resource-profile-fixture-manifest/2", manifest.path("schema").asText());
        assertEquals(10, manifest.withArray("records").size());
        assertEquals(5L, manifest.withArray("records").findValuesAsText("resource_kind").stream().filter("model"::equals).count());
        assertEquals(5L, manifest.withArray("records").findValuesAsText("resource_kind").stream().filter("dataset"::equals).count());

        for (JsonNode record : manifest.withArray("records")) {
            JsonNode snapshot = readAndVerify(root, record, true);
            JsonNode payload = snapshot.path("payload");
            assertEquals("huggingface", snapshot.path("provider").asText());
            assertEquals(record.path("resource_kind").asText(), snapshot.path("resource_kind").asText());
            assertEquals(record.path("observed").path("canonical_id").asText(), payload.path("id").asText());
            assertEquals(record.path("observed").path("revision").asText(), payload.path("sha").asText());

            ResourceProfileDraft.P0Candidate candidate = ResourceProfileDraft.fromHuggingFace(
                    payload, record.path("resource_kind").asText(), record.path("fixture").asText(),
                    record.path("source_file_sha256").asText(), Instant.EPOCH).toPendingP0Candidate();
            assertEquals("pending", candidate.authorizationStatus());
            assertNull(candidate.licenseExpressionId());
        }
    }

    @Test
    void missing_and_conflicting_examples_do_not_upgrade_authorization_or_license() throws Exception {
        Path root = fixtureRoot();
        JsonNode manifest = JSON.readTree(root.resolve("manifest.json").toFile());
        assertEquals(4, manifest.withArray("counterexamples").size());

        for (JsonNode example : manifest.withArray("counterexamples")) {
            JsonNode snapshot = readAndVerify(root, example, false);
            if (example.has("expected_error")) continue;
            JsonNode payload = snapshot.path("payload");
            ResourceProfileDraft.P0Candidate candidate = ResourceProfileDraft.fromHuggingFace(
                    payload, snapshot.path("resource_kind").asText(), example.path("fixture").asText(),
                    example.path("source_file_sha256").asText(), Instant.EPOCH).toPendingP0Candidate();
            assertEquals("pending", candidate.authorizationStatus());
            assertNull(candidate.licenseExpressionId());
            assertFalse(candidate.evidence().isEmpty());
        }
    }

    @Test
    void illegal_identity_fixture_is_rejected_without_network_or_conclusion() throws Exception {
        Path root = fixtureRoot();
        JsonNode manifest = JSON.readTree(root.resolve("manifest.json").toFile());
        JsonNode example = manifest.withArray("counterexamples").get(3);
        JsonNode snapshot = readAndVerify(root, example, false);

        assertEquals("metadata_invalid", example.path("expected_error").asText());
        assertThrows(IllegalArgumentException.class, () -> ResourceProfileDraft.fromHuggingFace(
                snapshot.path("payload"), snapshot.path("resource_kind").asText(),
                example.path("fixture").asText(), example.path("source_file_sha256").asText(), Instant.EPOCH));
    }

    private JsonNode readAndVerify(Path root, JsonNode entry, boolean requireObservationHash) throws Exception {
        Path fixture = root.resolve(entry.path("fixture").asText()).normalize();
        assertTrue(fixture.startsWith(root) && Files.isRegularFile(fixture));
        String digest = sha256(Files.readAllBytes(fixture));
        assertEquals(entry.path("source_file_sha256").asText(), digest);
        if (requireObservationHash) assertEquals(entry.path("source_observation_sha256").asText(), digest);
        return JSON.readTree(fixture.toFile());
    }

    private Path fixtureRoot() {
        Path cursor = Path.of(System.getProperty("user.dir")).toAbsolutePath().normalize();
        while (cursor != null) {
            Path candidate = cursor.resolve("tests/fixtures/huggingface/resource-profile-v2");
            if (Files.isDirectory(candidate)) return candidate;
            cursor = cursor.getParent();
        }
        throw new IllegalStateException("Hugging Face resource-profile v2 fixture directory was not found.");
    }

    private String sha256(byte[] data) throws Exception {
        byte[] hash = MessageDigest.getInstance("SHA-256").digest(data);
        StringBuilder value = new StringBuilder(64);
        for (byte b : hash) value.append(String.format("%02x", b));
        return value.toString();
    }
}
