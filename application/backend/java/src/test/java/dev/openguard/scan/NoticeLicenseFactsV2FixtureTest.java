package dev.openguard.scan;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.networknt.schema.SchemaRegistry;
import com.networknt.schema.SchemaRegistryConfig;
import com.networknt.schema.dialect.Dialects;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;

/** Independent structural checks for the B03/B04 v2 facts; no NoticeDraft is created. */
class NoticeLicenseFactsV2FixtureTest {
    private static final ObjectMapper JSON = new ObjectMapper();

    @Test
    void schema_and_conservative_machine_fields_are_closed() throws Exception {
        JsonNode root = JSON.readTree(fixtureRoot().resolve("facts.json").toFile());
        SchemaRegistryConfig config =
                SchemaRegistryConfig.builder().formatAssertionsEnabled(true).failFast(false).build();
        SchemaRegistry registry = SchemaRegistry.withDialect(
                Dialects.getDraft202012(), builder -> builder.schemaRegistryConfig(config));
        var schema = registry.getSchema(JSON.readTree(fixtureRoot().resolve("schema.json").toFile()));
        schema.initializeValidators();
        assertTrue(schema.validate(root).isEmpty(), schema.validate(root).toString());

        assertEquals("openguard.notice-license-facts/2", root.path("schema_version").asText());
        assertEquals(10, root.withArray("evidence").size());
        assertEquals(8, root.withArray("facts").size());
        assertEquals(8, root.withArray("report_v2_rows").size());
        assertFalse(root.path("policies").path("license_expression_autofill").asBoolean());
        assertFalse(root.path("policies").path("gap_is_noncompliance").asBoolean());
        assertFalse(root.path("policies").path("notice_absence_is_violation").asBoolean());

        Set<String> evidenceIds = uniqueIds(root.withArray("evidence"), "evidence_id");
        Set<String> factIds = uniqueIds(root.withArray("facts"), "fact_id");
        Set<String> scopes = new HashSet<>();
        for (JsonNode evidence : root.withArray("evidence")) {
            scopes.add(evidence.path("content_scope").asText());
            assertTrue(evidence.path("source_file_sha256").asText().matches("[0-9a-f]{64}"));
            assertTrue(evidence.path("selected_content_sha256").asText().matches("[0-9a-f]{64}"));
            assertTrue(evidence.path("captured_at").asText().endsWith("Z"));
            assertEquals("openguard-b03-b04-facts", evidence.path("producer").path("name").asText());
        }
        assertEquals(Set.of("whole_file", "archive_entry", "json_pointer_value"), scopes);

        Map<String, JsonNode> rows = new HashMap<>();
        for (JsonNode row : root.withArray("report_v2_rows")) {
            assertTrue(rows.put(row.path("subject_fact_id").asText(), row) == null);
            assertTrue(factIds.contains(row.path("subject_fact_id").asText()));
        }
        for (JsonNode fact : root.withArray("facts")) {
            assertEquals("pending", fact.path("authorization_status").asText());
            assertEquals("pending_human_review", fact.path("review_status").asText());
            for (JsonNode observation : fact.withArray("license_observations")) {
                assertTrue(observation.path("license_expression_id").isNull());
                requireReferences(observation.withArray("evidence_ids"), evidenceIds);
            }
            for (String name : new String[] {"license", "notice", "copyright"}) {
                JsonNode relationship = fact.path("relationships").path(name);
                assertEquals("pending_review", relationship.path("applicability").asText());
                requireReferences(relationship.withArray("evidence_ids"), evidenceIds);
                assertEquals(relationship.path("state").asText().equals("gap"), !relationship.path("gap_code").isNull());
            }
            JsonNode row = rows.get(fact.path("fact_id").asText());
            assertNotNull(row);
            assertEquals(fact.path("authorization_status"), row.path("authorization_status"));
            assertEquals(stringSet(fact.withArray("gaps")), stringSet(row.withArray("gap_codes")));
            assertTrue(row.withArray("license_expression_ids").isEmpty());
        }
    }

    @Test
    void source_package_is_byte_pinned_without_mutating_v1() throws Exception {
        JsonNode root = JSON.readTree(fixtureRoot().resolve("facts.json").toFile());
        JsonNode source = root.path("source_package");
        Path sourcePath = projectRoot().resolve(source.path("path").asText()).normalize();
        assertTrue(sourcePath.startsWith(projectRoot()));
        assertEquals(source.path("source_file_sha256").asText(), sha256(Files.readAllBytes(sourcePath)));
        assertEquals("e2d8c016ef5f4cfcddd23abb0205ec41c7cf3db1", source.path("fixed_commit").asText());
    }

    private Set<String> uniqueIds(JsonNode values, String field) {
        Set<String> ids = new HashSet<>();
        values.forEach(value -> assertTrue(ids.add(value.path(field).asText()), "duplicate " + field));
        return ids;
    }

    private void requireReferences(JsonNode references, Set<String> known) {
        references.forEach(reference -> assertTrue(known.contains(reference.asText()), reference.asText()));
    }

    private Set<String> stringSet(JsonNode values) {
        Set<String> result = new HashSet<>();
        values.forEach(value -> result.add(value.asText()));
        return result;
    }

    private Path fixtureRoot() {
        return projectRoot().resolve("tests/fixtures/notice-license-facts-v2");
    }

    private Path projectRoot() {
        Path cursor = Path.of(System.getProperty("user.dir")).toAbsolutePath().normalize();
        while (cursor != null) {
            if (Files.isRegularFile(cursor.resolve("LICENSE")) && Files.isDirectory(cursor.resolve("backend/java"))) {
                return cursor;
            }
            cursor = cursor.getParent();
        }
        throw new IllegalStateException("OpenGuard project root was not found.");
    }

    private String sha256(byte[] data) throws Exception {
        return java.util.HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(data));
    }
}
