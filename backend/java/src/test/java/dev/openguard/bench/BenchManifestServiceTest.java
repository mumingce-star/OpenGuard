package dev.openguard.bench;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class BenchManifestServiceTest {
  private final ObjectMapper mapper = new ObjectMapper();
  private final BenchManifestService service = new BenchManifestService();

  @TempDir Path tempDir;

  @Test
  void acceptsValidDevelopmentManifest() throws Exception {
    Path manifest = writeManifest("development");
    ValidationOutcome outcome = service.validate(manifest);

    assertEquals(0, outcome.exitCode());
    assertTrue(outcome.report().valid());
    assertEquals("development", outcome.report().derivedTier());
    assertTrue(outcome.report().diagnostics().isEmpty());
  }

  @Test
  void rejectsUnknownSchemaProperty() throws Exception {
    Path manifest = writeManifest("development");
    ObjectNode root = (ObjectNode) mapper.readTree(manifest.toFile());
    root.put("unexpected", true);
    mapper.writeValue(manifest.toFile(), root);

    ValidationOutcome outcome = service.validate(manifest);

    assertEquals(1, outcome.exitCode());
    assertFalse(outcome.report().valid());
    assertTrue(hasCodePrefix(outcome, "BENCH_SCHEMA_"));
  }

  @Test
  void rejectsDuplicateKeysAndTrailingJsonValuesAtParseBoundary() throws Exception {
    Path manifest = writeManifest("development");
    String original = Files.readString(manifest, StandardCharsets.UTF_8);
    Files.writeString(
        manifest,
        original.replaceFirst(
            "\\{",
            "{\\\"schema_version\\\":\\\"openguard-bench-manifest/2.0\\\","),
        StandardCharsets.UTF_8);

    ValidationOutcome duplicate = service.validate(manifest);
    assertEquals(2, duplicate.exitCode());
    assertTrue(hasCode(duplicate, "BENCH_INPUT_JSON_INVALID"));

    Files.writeString(manifest, original + "{}", StandardCharsets.UTF_8);
    ValidationOutcome trailing = service.validate(manifest);
    assertEquals(2, trailing.exitCode());
    assertTrue(hasCode(trailing, "BENCH_INPUT_JSON_INVALID"));
  }

  @Test
  void rejectsDuplicateIdsAndCrossSplitFamily() throws Exception {
    Path manifest = writeManifest("development");
    ObjectNode root = (ObjectNode) mapper.readTree(manifest.toFile());
    ArrayNode cases = (ArrayNode) root.path("cases");
    ObjectNode duplicate = cases.get(0).deepCopy();
    duplicate.put("split", "holdout");
    duplicate.put("content_sha256", "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
    cases.add(duplicate);
    mapper.writeValue(manifest.toFile(), root);

    ValidationOutcome outcome = service.validate(manifest);

    assertEquals(1, outcome.exitCode());
    assertTrue(hasCode(outcome, "BENCH_DUPLICATE_ID"));
    assertTrue(hasCode(outcome, "BENCH_SPLIT_FAMILY_LEAKAGE"));
  }

  @Test
  void rejectsUnsafeArtifactPath() throws Exception {
    Path manifest = writeManifest("development");
    ObjectNode root = (ObjectNode) mapper.readTree(manifest.toFile());
    ((ObjectNode) root.path("artifacts").get(0)).put("path", "../outside.json");
    mapper.writeValue(manifest.toFile(), root);

    ValidationOutcome outcome = service.validate(manifest);

    assertEquals(1, outcome.exitCode());
    assertTrue(hasCode(outcome, "BENCH_ARTIFACT_PATH_UNSAFE"));
  }

  @Test
  void rejectsArtifactHashMismatch() throws Exception {
    Path manifest = writeManifest("development");
    Files.writeString(tempDir.resolve("artifacts/gold.json"), "tampered", StandardCharsets.UTF_8);

    ValidationOutcome outcome = service.validate(manifest);

    assertEquals(1, outcome.exitCode());
    assertTrue(hasCode(outcome, "BENCH_ARTIFACT_SIZE_MISMATCH")
        || hasCode(outcome, "BENCH_ARTIFACT_HASH_MISMATCH"));
  }

  @Test
  void validatesSecondRevisionAndBindsParentHash() throws Exception {
    Path manifest = writeSecondRevision();

    ValidationOutcome valid = service.validate(manifest);
    assertEquals(0, valid.exitCode(), valid.report().diagnostics().toString());

    Files.writeString(tempDir.resolve("parent.json"), "\n", StandardCharsets.UTF_8,
        java.nio.file.StandardOpenOption.APPEND);
    ValidationOutcome tampered = service.validate(manifest);
    assertEquals(1, tampered.exitCode());
    assertTrue(hasCode(tampered, "BENCH_PARENT_HASH_MISMATCH"));
  }

  @Test
  void rejectsLaterRevisionWithoutAmendment() throws Exception {
    Path manifest = writeSecondRevision();
    ObjectNode root = (ObjectNode) mapper.readTree(manifest.toFile());
    ((ArrayNode) root.path("amendments")).removeAll();
    mapper.writeValue(manifest.toFile(), root);

    ValidationOutcome outcome = service.validate(manifest);

    assertEquals(1, outcome.exitCode());
    assertTrue(hasCode(outcome, "BENCH_AMENDMENT_REQUIRED"));
  }

  @Test
  void rejectsIncludedPendingCase() throws Exception {
    Path manifest = writeManifest("development");
    ObjectNode root = (ObjectNode) mapper.readTree(manifest.toFile());
    ((ObjectNode) root.path("cases").get(0)).put("authorization_status", "pending");
    mapper.writeValue(manifest.toFile(), root);

    ValidationOutcome outcome = service.validate(manifest);

    assertEquals(1, outcome.exitCode());
    assertTrue(hasCode(outcome, "BENCH_CASE_NOT_AUTHORIZED"));
  }

  @Test
  void returnsPolicyExitWhenRequestedTierIsUnavailable() throws Exception {
    Path manifest = writeManifest("reportable_independent");

    ValidationOutcome outcome = service.validate(manifest);

    assertEquals(3, outcome.exitCode());
    assertTrue(outcome.report().valid());
    assertEquals("development", outcome.report().derivedTier());
    assertTrue(hasCode(outcome, "BENCH_TIER_NOT_MET"));
  }

  @Test
  void holdoutDevelopmentExposurePreventsReportableTier() throws Exception {
    Path manifest = writeManifest("reportable_single_human");
    ObjectNode root = (ObjectNode) mapper.readTree(manifest.toFile());
    ((ObjectNode) root.path("cases").get(0)).put("split", "holdout");
    ObjectNode exposure = mapper.createObjectNode();
    exposure.put("split", "holdout");
    exposure.put("actor", "actor_rules");
    exposure.put("purpose", "rule_development");
    exposure.put("occurred_at", "2026-09-18T00:30:00Z");
    exposure.put("artifact_id", "art_source");
    ((ArrayNode) root.path("governance").path("exposures")).add(exposure);
    ((ObjectNode) root.path("evaluations").get(0)).put("target_split", "holdout");
    mapper.writeValue(manifest.toFile(), root);

    ValidationOutcome outcome = service.validate(manifest);

    assertEquals(3, outcome.exitCode());
    assertTrue(hasCode(outcome, "BENCH_HOLDOUT_EXPOSED"));
  }

  @Test
  void cliWritesOneStableJsonDocument() throws Exception {
    Path manifest = writeManifest("development");
    ByteArrayOutputStream stdout = new ByteArrayOutputStream();
    ByteArrayOutputStream stderr = new ByteArrayOutputStream();

    int exit = BenchManifestCli.run(
        new String[] {"validate", manifest.toString()},
        new PrintStream(stdout, true, StandardCharsets.UTF_8),
        new PrintStream(stderr, true, StandardCharsets.UTF_8));

    assertEquals(0, exit);
    JsonNode report = mapper.readTree(stdout.toString(StandardCharsets.UTF_8));
    assertEquals("openguard-bench-validation-report/1.0", report.path("contract_version").asText());
    assertEquals("", stderr.toString(StandardCharsets.UTF_8));

    ByteArrayOutputStream repeated = new ByteArrayOutputStream();
    int repeatedExit =
        BenchManifestCli.run(
            new String[] {"validate", manifest.toString()},
            new PrintStream(repeated, true, StandardCharsets.UTF_8),
            new PrintStream(new ByteArrayOutputStream()));
    assertEquals(0, repeatedExit);
    assertEquals(stdout.toString(StandardCharsets.UTF_8), repeated.toString(StandardCharsets.UTF_8));
  }

  @Test
  void cliUsesExitTwoForMalformedJsonWithoutLeakingPath() throws Exception {
    Path manifest = tempDir.resolve("secret-manifest.json");
    Files.writeString(manifest, "{bad json", StandardCharsets.UTF_8);
    ByteArrayOutputStream stdout = new ByteArrayOutputStream();

    int exit = BenchManifestCli.run(
        new String[] {"validate", manifest.toString()},
        new PrintStream(stdout, true, StandardCharsets.UTF_8),
        new PrintStream(new ByteArrayOutputStream()));

    String output = stdout.toString(StandardCharsets.UTF_8);
    assertEquals(2, exit);
    assertFalse(output.contains(tempDir.toAbsolutePath().toString()));
    assertTrue(output.contains("BENCH_INPUT_JSON_INVALID"));
  }

  private Path writeManifest(String requestedTier) throws Exception {
    Path artifactsDir = Files.createDirectories(tempDir.resolve("artifacts"));
    ArrayNode artifacts = mapper.createArrayNode();
    artifacts.add(writeArtifact(artifactsDir, "art_source", "source_index", "source.json", "{}"));
    artifacts.add(writeArtifact(artifactsDir, "art_gold", "gold", "gold.json", "{}"));
    artifacts.add(writeArtifact(artifactsDir, "art_policy", "matching_policy", "policy.json", "{}"));
    artifacts.add(writeArtifact(artifactsDir, "art_config", "run_config", "config.json", "{}"));
    artifacts.add(writeArtifact(artifactsDir, "art_prediction", "prediction", "prediction.json", "{}"));
    artifacts.add(writeArtifact(artifactsDir, "art_result", "result", "result.json", "{}"));

    ObjectNode root = mapper.createObjectNode();
    root.put("schema_version", "openguard-bench-manifest/2.0");

    ObjectNode identity = root.putObject("identity");
    identity.put("manifest_id", "bmf_test_manifest");
    identity.put("revision", 1);
    identity.put("created_at", "2026-09-18T00:00:00Z");
    identity.putNull("parent");

    ObjectNode benchmark = root.putObject("benchmark");
    benchmark.put("benchmark_id", "bench_test");
    benchmark.put("title", "Bench test fixture");
    benchmark.putArray("task_types").add("component_detection");
    benchmark.put("label_set_version", "labels-1");
    benchmark.put("case_granularity", "repository");
    benchmark.putObject("scope").putArray("included").add("fixtures");
    ((ObjectNode) benchmark.path("scope")).putArray("excluded");
    benchmark.put("matching_policy_artifact_id", "art_policy");

    root.set("artifacts", artifacts);
    ObjectNode benchCase = root.putArray("cases").addObject();
    benchCase.put("case_id", "case_alpha");
    benchCase.put("family_id", "family_alpha");
    benchCase.put("content_sha256", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
    benchCase.put("split", "dev");
    benchCase.putArray("source_artifact_ids").add("art_source");
    benchCase.put("gold_artifact_id", "art_gold");
    benchCase.put("authorization_status", "verified");
    benchCase.put("included", true);

    ObjectNode governance = root.putObject("governance");
    governance.putArray("reviews");
    governance.putArray("exposures");
    governance.putArray("disputes");
    ObjectNode freeze = governance.putObject("freeze");
    freeze.put("status", "frozen");
    freeze.put("frozen_at", "2026-09-18T00:10:00Z");
    freeze.putArray("artifact_ids").add("art_gold").add("art_policy");
    freeze.put("frozen_by_actor_type", "human");

    root.putArray("amendments");
    ObjectNode evaluation = root.putArray("evaluations").addObject();
    evaluation.put("evaluation_id", "eval_alpha");
    evaluation.put("benchmark_revision", 1);
    evaluation.put("target_split", "dev");
    evaluation.put("system_revision", "git:0123456789abcdef");
    evaluation.put("gold_artifact_id", "art_gold");
    evaluation.put("matching_policy_artifact_id", "art_policy");
    evaluation.put("run_config_artifact_id", "art_config");
    evaluation.put("prediction_artifact_id", "art_prediction");
    evaluation.put("result_artifact_id", "art_result");
    evaluation.put("started_at", "2026-09-18T01:00:00Z");
    evaluation.put("finished_at", "2026-09-18T01:05:00Z");
    evaluation.put("requested_tier", requestedTier);

    Path manifest = tempDir.resolve("manifest.json");
    mapper.writerWithDefaultPrettyPrinter().writeValue(manifest.toFile(), root);
    return manifest;
  }

  private Path writeSecondRevision() throws Exception {
    Path firstRevision = writeManifest("development");
    Path parent = tempDir.resolve("parent.json");
    Files.move(firstRevision, parent);
    ObjectNode root = (ObjectNode) mapper.readTree(parent.toFile());

    ObjectNode identity = (ObjectNode) root.path("identity");
    identity.put("revision", 2);
    ObjectNode parentBinding = identity.putObject("parent");
    parentBinding.put("path", "parent.json");
    parentBinding.put(
        "sha256",
        HexFormat.of().formatHex(
            MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(parent))));
    parentBinding.put("manifest_id", "bmf_test_manifest");
    parentBinding.put("revision", 1);

    ObjectNode amendmentArtifact =
        writeArtifact(
            tempDir.resolve("artifacts"),
            "art_amendment",
            "amendment",
            "amendment.json",
            "{}");
    ((ArrayNode) root.path("artifacts")).add(amendmentArtifact);
    ObjectNode amendment = ((ArrayNode) root.path("amendments")).addObject();
    amendment.put("amendment_id", "amendment_one");
    amendment.put("target_type", "gold");
    amendment.put("target_id", "art_gold");
    amendment.put(
        "old_sha256", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
    amendment.put(
        "new_sha256", "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
    amendment.put("reason_code", "label_correction");
    amendment.put("description", "Corrected a reviewed label.");
    amendment.put("proposed_by_actor_type", "ai");
    amendment.put("approved_by_actor_type", "human");
    amendment.put("artifact_id", "art_amendment");
    amendment.put("amended_at", "2026-09-18T00:20:00Z");
    ((ObjectNode) root.path("evaluations").get(0)).put("benchmark_revision", 2);

    Path manifest = tempDir.resolve("manifest.json");
    mapper.writerWithDefaultPrettyPrinter().writeValue(manifest.toFile(), root);
    return manifest;
  }

  private ObjectNode writeArtifact(
      Path directory, String id, String role, String fileName, String content) throws Exception {
    byte[] data = content.getBytes(StandardCharsets.UTF_8);
    Files.write(directory.resolve(fileName), data);
    ObjectNode artifact = mapper.createObjectNode();
    artifact.put("artifact_id", id);
    artifact.put("role", role);
    artifact.put("path", "artifacts/" + fileName);
    artifact.put("media_type", "application/json");
    artifact.put("size_bytes", data.length);
    artifact.put("sha256", HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(data)));
    artifact.put("redistribution", "repository_allowed");
    return artifact;
  }

  private boolean hasCode(ValidationOutcome outcome, String code) {
    return outcome.report().diagnostics().stream().anyMatch(d -> d.code().equals(code));
  }

  private boolean hasCodePrefix(ValidationOutcome outcome, String prefix) {
    return outcome.report().diagnostics().stream().anyMatch(d -> d.code().startsWith(prefix));
  }
}
