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
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HashMap;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.Map;
import java.util.Set;
import java.util.zip.ZipFile;
import org.junit.jupiter.api.Test;

/** Verifies the facts-only NOTICE/license draft without producing a Report V2 snapshot. */
class NoticeLicenseFactsFixtureTest {
    private static final ObjectMapper JSON = new ObjectMapper();

    @Test
    void facts_validate_and_report_rows_close_all_references() throws Exception {
        Path packageRoot = fixtureRoot();
        JsonNode root = JSON.readTree(packageRoot.resolve("facts.json").toFile());
        SchemaRegistryConfig config =
                SchemaRegistryConfig.builder().formatAssertionsEnabled(true).failFast(false).build();
        SchemaRegistry registry = SchemaRegistry.withDialect(
                Dialects.getDraft202012(), builder -> builder.schemaRegistryConfig(config));
        var schema = registry.getSchema(JSON.readTree(packageRoot.resolve("schema.json").toFile()));
        schema.initializeValidators();
        assertTrue(schema.validate(root).isEmpty(), schema.validate(root).toString());

        assertEquals("openguard.notice-license-facts/1", root.path("schema_version").asText());
        assertEquals("draft_facts_only", root.path("package_status").asText());
        assertEquals(8, root.withArray("facts").size());
        assertEquals(8, root.withArray("report_v2_rows").size());

        Set<String> evidenceIds = uniqueIds(root.withArray("evidence"), "evidence_id");
        Set<String> factIds = uniqueIds(root.withArray("facts"), "fact_id");
        uniqueIds(root.withArray("report_v2_rows"), "row_id");
        Set<String> categories = new HashSet<>();
        boolean apacheNotice = false;
        boolean mitAttribution = false;
        boolean bsdAttribution = false;
        boolean hasGap = false;

        for (JsonNode fact : root.withArray("facts")) {
            categories.add(fact.path("subject").path("category").asText());
            assertEquals("pending_human_review", fact.path("review_status").asText());
            for (JsonNode observation : fact.withArray("license_observations")) {
                assertTrue(observation.path("license_expression_id").isNull());
                requireReferences(observation.withArray("evidence_ids"), evidenceIds);
                String raw = observation.path("raw_value").toString();
                apacheNotice |= raw.contains("Apache License Version 2.0")
                        && fact.path("relationships").path("notice").path("state").asText().equals("observed");
                mitAttribution |= raw.contains("MIT License")
                        && fact.path("relationships").path("copyright").path("state").asText().equals("observed");
                bsdAttribution |= raw.contains("BSD 3-Clause")
                        && fact.path("relationships").path("copyright").path("state").asText().equals("observed");
            }
            for (String relationship : new String[] {"license", "notice", "copyright"}) {
                JsonNode value = fact.path("relationships").path(relationship);
                requireReferences(value.withArray("evidence_ids"), evidenceIds);
                if (value.path("state").asText().equals("gap")) {
                    hasGap = true;
                    assertTrue(value.path("evidence_ids").isEmpty());
                    assertFalse(value.path("gap_code").isNull());
                } else {
                    assertTrue(value.path("gap_code").isNull());
                    assertFalse(value.path("evidence_ids").isEmpty());
                }
            }
        }

        assertEquals(Set.of("root_project", "dependency", "ai_resource"), categories);
        assertTrue(apacheNotice, "Apache LICENSE+NOTICE demonstration is required");
        assertTrue(mitAttribution, "MIT attribution demonstration is required");
        assertTrue(bsdAttribution, "BSD attribution demonstration is required");
        assertTrue(hasGap, "Missing evidence must be represented as a gap");

        for (JsonNode row : root.withArray("report_v2_rows")) {
            assertTrue(factIds.contains(row.path("subject_fact_id").asText()));
            assertEquals("待核验", row.path("compliance_status").asText());
            requireReferences(row.withArray("evidence_ids"), evidenceIds);
        }
    }

    @Test
    void repository_provider_and_maven_sources_match_recorded_sha256() throws Exception {
        Path projectRoot = projectRoot();
        JsonNode root = JSON.readTree(fixtureRoot().resolve("facts.json").toFile());
        Map<String, ArchiveSource> archives = archiveSources(projectRoot);

        for (JsonNode evidence : root.withArray("evidence")) {
            String id = evidence.path("evidence_id").asText();
            String kind = evidence.path("kind").asText();
            if (kind.equals("repository_file")) {
                Path source = projectRoot.resolve(evidence.path("locator").asText()).normalize();
                assertTrue(source.startsWith(projectRoot));
                assertEquals(evidence.path("content_sha256").asText(), sha256(Files.readAllBytes(source)));
            } else if (kind.equals("provider_snapshot")) {
                String locator = evidence.path("locator").asText();
                Path source = projectRoot.resolve(locator.substring(0, locator.indexOf('#'))).normalize();
                assertTrue(source.startsWith(projectRoot));
                assertEquals(evidence.path("content_sha256").asText(), sha256(Files.readAllBytes(source)));
            } else {
                ArchiveSource source = archives.get(id);
                assertNotNull(source, id);
                assertEquals(evidence.path("container_sha256").asText(), sha256(Files.readAllBytes(source.archive())));
                try (ZipFile zip = new ZipFile(source.archive().toFile())) {
                    var entry = zip.getEntry(source.entry());
                    assertNotNull(entry, source.entry());
                    try (InputStream stream = zip.getInputStream(entry)) {
                        assertEquals(evidence.path("content_sha256").asText(), sha256(stream.readAllBytes()));
                    }
                }
            }
        }
    }

    private Map<String, ArchiveSource> archiveSources(Path projectRoot) {
        Path repository = projectRoot.resolve(".tools/m2-java-migration");
        Map<String, ArchiveSource> values = new HashMap<>();
        Path jackson = repository.resolve("com/fasterxml/jackson/core/jackson-databind/2.21.5/jackson-databind-2.21.5.jar");
        values.put("ev.jackson.license", new ArchiveSource(jackson, "META-INF/LICENSE"));
        values.put("ev.jackson.notice", new ArchiveSource(jackson, "META-INF/NOTICE"));
        Path spring = repository.resolve("org/springframework/boot/spring-boot/4.1.1/spring-boot-4.1.1.jar");
        values.put("ev.springboot.license", new ArchiveSource(spring, "META-INF/LICENSE.txt"));
        values.put("ev.springboot.notice", new ArchiveSource(spring, "META-INF/NOTICE.txt"));
        values.put("ev.hamcrest.license", new ArchiveSource(
                repository.resolve("org/hamcrest/hamcrest/3.0/hamcrest-3.0.jar"), "META-INF/LICENSE"));
        values.put("ev.mockito.license", new ArchiveSource(
                repository.resolve("org/mockito/mockito-core/5.23.0/mockito-core-5.23.0.jar"), "LICENSE"));
        return values;
    }

    private Set<String> uniqueIds(JsonNode values, String field) {
        Set<String> ids = new HashSet<>();
        values.forEach(value -> assertTrue(ids.add(value.path(field).asText()), "duplicate " + field));
        return ids;
    }

    private void requireReferences(JsonNode references, Set<String> known) {
        references.forEach(reference -> assertTrue(known.contains(reference.asText()), reference.asText()));
    }

    private Path fixtureRoot() {
        return projectRoot().resolve("tests/fixtures/notice-license-facts-v1");
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
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(data));
    }

    private record ArchiveSource(Path archive, String entry) {}
}
