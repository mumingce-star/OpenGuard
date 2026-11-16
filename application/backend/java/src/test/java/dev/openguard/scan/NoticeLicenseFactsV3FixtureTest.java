package dev.openguard.scan;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.networknt.schema.SchemaRegistry;
import com.networknt.schema.SchemaRegistryConfig;
import com.networknt.schema.dialect.Dialects;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashSet;
import java.util.Set;
import org.junit.jupiter.api.Test;

/** Cross-runtime closure checks for the B03/B04 real-inventory v3 fixture. */
class NoticeLicenseFactsV3FixtureTest {
    private static final ObjectMapper JSON = new ObjectMapper();

    @Test
    void real_inventory_is_schema_valid_source_bound_and_conservative() throws Exception {
        JsonNode root = JSON.readTree(fixtureRoot().resolve("facts.json").toFile());
        SchemaRegistryConfig config = SchemaRegistryConfig.builder().formatAssertionsEnabled(true).failFast(false).build();
        SchemaRegistry registry = SchemaRegistry.withDialect(Dialects.getDraft202012(), builder -> builder.schemaRegistryConfig(config));
        var schema = registry.getSchema(JSON.readTree(fixtureRoot().resolve("schema.json").toFile()));
        schema.initializeValidators();
        assertTrue(schema.validate(root).isEmpty(), schema.validate(root).toString());
        assertEquals("openguard.notice-license-facts/3", root.path("schema_version").asText());
        assertEquals(31, root.withArray("facts").size());
        assertEquals(31, root.withArray("evidence").size());
        assertEquals(31, root.withArray("report_v3_rows").size());

        Set<String> evidenceIds = new HashSet<>();
        for (JsonNode evidence : root.withArray("evidence")) {
            assertTrue(evidenceIds.add(evidence.path("evidence_id").asText()));
            assertTrue(evidence.path("source_file_sha256").asText().matches("[0-9a-f]{64}"));
            assertTrue(evidence.path("selected_content_sha256").asText().matches("[0-9a-f]{64}"));
            assertEquals("3.0.0", evidence.path("producer").path("version").asText());
        }
        for (JsonNode fact : root.withArray("facts")) {
            assertEquals("pending", fact.path("authorization_status").asText());
            assertTrue(fact.path("license_expression_id").isNull());
            assertTrue(fact.withArray("fact_provenance_evidence_ids").size() > 0);
            for (JsonNode id : fact.withArray("fact_provenance_evidence_ids")) assertTrue(evidenceIds.contains(id.asText()));
            for (String name : new String[] {"license", "notice", "copyright"}) {
                JsonNode relation = fact.path("relationships").path(name);
                assertTrue(Set.of("text_observed", "provider_declared_unverified", "gap").contains(relation.path("state").asText()));
                if ("gap".equals(relation.path("state").asText())) assertEquals(0, relation.withArray("evidence_ids").size());
            }
        }
    }

    private Path fixtureRoot() { return projectRoot().resolve("tests/fixtures/notice-license-facts-v3"); }

    private Path projectRoot() {
        Path cursor = Path.of(System.getProperty("user.dir")).toAbsolutePath().normalize();
        while (cursor != null) {
            if (Files.isRegularFile(cursor.resolve("LICENSE")) && Files.isDirectory(cursor.resolve("backend/java"))) return cursor;
            cursor = cursor.getParent();
        }
        throw new IllegalStateException("OpenGuard project root was not found.");
    }
}
