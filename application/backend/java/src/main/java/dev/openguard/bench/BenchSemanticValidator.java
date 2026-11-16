package dev.openguard.bench;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

final class BenchSemanticValidator {
  private static final Set<String> HOLDOUT_DEVELOPMENT_PURPOSES =
      Set.of("error_analysis", "rule_development", "prompt_development",
          "model_training", "threshold_tuning");
  private static final Set<String> HUMAN_APPROVAL_TARGETS =
      Set.of("case", "gold", "matching_policy", "split", "review", "freeze");

  record Result(List<Diagnostic> diagnostics, MetricTier derivedTier) {}

  private final ObjectMapper mapper;
  private final ArtifactIntegrityValidator artifactValidator;

  BenchSemanticValidator(ObjectMapper mapper, ArtifactIntegrityValidator artifactValidator) {
    this.mapper = mapper;
    this.artifactValidator = artifactValidator;
  }

  Result validate(Path manifestPath, JsonNode root) {
    List<Diagnostic> diagnostics = new ArrayList<>();
    Map<String, JsonNode> artifacts =
        index(root.path("artifacts"), "artifact_id", "/artifacts", diagnostics);
    Map<String, JsonNode> cases = index(root.path("cases"), "case_id", "/cases", diagnostics);
    JsonNode governance = root.path("governance");
    Map<String, JsonNode> reviews =
        index(governance.path("reviews"), "review_id", "/governance/reviews", diagnostics);
    Map<String, JsonNode> disputes =
        index(governance.path("disputes"), "dispute_id", "/governance/disputes", diagnostics);
    index(root.path("amendments"), "amendment_id", "/amendments", diagnostics);
    index(root.path("evaluations"), "evaluation_id", "/evaluations", diagnostics);

    validateArtifactReferences(root, artifacts, cases, reviews, diagnostics);
    boolean splitClean = validateSplitIsolation(root.path("cases"), diagnostics);
    boolean holdoutExposed = validateHoldoutExposure(governance.path("exposures"), diagnostics);
    validateGovernance(governance, diagnostics);
    validateCaseAuthorization(root.path("cases"), diagnostics);
    validateAmendments(root.path("amendments"), artifacts, diagnostics);
    validateAmendmentRevision(root, diagnostics);
    validateEvaluations(root, artifacts, diagnostics);
    validateParent(manifestPath, root.path("identity"), diagnostics);

    boolean policyFrozen = isPolicyFrozen(root, artifacts);
    boolean goldFrozen = isGoldFrozen(root, artifacts);
    boolean noBlockingDispute = hasNoBlockingDispute(governance.path("disputes"));
    Set<String> includedCases = includedCaseIds(root.path("cases"));
    boolean singleHuman = hasSingleHumanBlindReview(governance.path("reviews"), includedCases);
    boolean independentHumans =
        hasIndependentHumanReviews(governance.path("reviews"), includedCases)
            && disputesAllowIndependentTier(governance, reviews, artifacts);

    MetricTier tier = MetricTier.SMOKE;
    if (splitClean && policyFrozen) tier = MetricTier.DEVELOPMENT;
    if (tier == MetricTier.DEVELOPMENT && goldFrozen && noBlockingDispute && !holdoutExposed) {
      if (singleHuman) tier = MetricTier.REPORTABLE_SINGLE_HUMAN;
      if (independentHumans) tier = MetricTier.REPORTABLE_INDEPENDENT;
    }
    return new Result(diagnostics, tier);
  }

  private Map<String, JsonNode> index(
      JsonNode array, String idField, String basePointer, List<Diagnostic> diagnostics) {
    Map<String, JsonNode> result = new LinkedHashMap<>();
    for (int i = 0; i < array.size(); i++) {
      JsonNode item = array.get(i);
      String id = item.path(idField).asText();
      if (result.putIfAbsent(id, item) != null) {
        diagnostics.add(error(
            "BENCH_DUPLICATE_ID", basePointer + "/" + i + "/" + idField,
            "Identifier must be unique within its namespace."));
      }
    }
    return result;
  }

  private void validateArtifactReferences(
      JsonNode root,
      Map<String, JsonNode> artifacts,
      Map<String, JsonNode> cases,
      Map<String, JsonNode> reviews,
      List<Diagnostic> diagnostics) {
    requireRole(
        artifacts,
        root.path("benchmark").path("matching_policy_artifact_id").asText(),
        "matching_policy",
        "/benchmark/matching_policy_artifact_id",
        diagnostics);

    JsonNode caseArray = root.path("cases");
    for (int i = 0; i < caseArray.size(); i++) {
      JsonNode item = caseArray.get(i);
      for (int j = 0; j < item.path("source_artifact_ids").size(); j++) {
        requireRole(
            artifacts,
            item.path("source_artifact_ids").get(j).asText(),
            "source_index",
            "/cases/" + i + "/source_artifact_ids/" + j,
            diagnostics);
      }
      requireRole(
          artifacts,
          item.path("gold_artifact_id").asText(),
          "gold",
          "/cases/" + i + "/gold_artifact_id",
          diagnostics);
    }

    JsonNode reviewArray = root.path("governance").path("reviews");
    for (int i = 0; i < reviewArray.size(); i++) {
      JsonNode review = reviewArray.get(i);
      requireRole(
          artifacts, review.path("artifact_id").asText(), "review",
          "/governance/reviews/" + i + "/artifact_id", diagnostics);
      if (review.has("blinded_packet_artifact_id")) {
        requireAnyRole(
            artifacts,
            review.path("blinded_packet_artifact_id").asText(),
            Set.of("source_index", "review"),
            "/governance/reviews/" + i + "/blinded_packet_artifact_id",
            diagnostics);
      }
      for (int j = 0; j < review.path("case_ids").size(); j++) {
        requireId(
            cases,
            review.path("case_ids").get(j).asText(),
            "/governance/reviews/" + i + "/case_ids/" + j,
            "case",
            diagnostics);
      }
    }

    JsonNode exposures = root.path("governance").path("exposures");
    for (int i = 0; i < exposures.size(); i++) {
      requireId(
          artifacts,
          exposures.get(i).path("artifact_id").asText(),
          "/governance/exposures/" + i + "/artifact_id",
          "artifact",
          diagnostics);
    }

    JsonNode disputeArray = root.path("governance").path("disputes");
    for (int i = 0; i < disputeArray.size(); i++) {
      JsonNode dispute = disputeArray.get(i);
      requireId(
          cases, dispute.path("case_id").asText(),
          "/governance/disputes/" + i + "/case_id", "case", diagnostics);
      for (int j = 0; j < dispute.path("review_ids").size(); j++) {
        requireId(
            reviews,
            dispute.path("review_ids").get(j).asText(),
            "/governance/disputes/" + i + "/review_ids/" + j,
            "review",
            diagnostics);
      }
      if (dispute.has("resolution_artifact_id")) {
        requireRole(
            artifacts,
            dispute.path("resolution_artifact_id").asText(),
            "resolution",
            "/governance/disputes/" + i + "/resolution_artifact_id",
            diagnostics);
      }
    }

    JsonNode freezeIds = root.path("governance").path("freeze").path("artifact_ids");
    for (int i = 0; i < freezeIds.size(); i++) {
      requireId(
          artifacts, freezeIds.get(i).asText(),
          "/governance/freeze/artifact_ids/" + i, "artifact", diagnostics);
    }
  }

  private boolean validateSplitIsolation(JsonNode cases, List<Diagnostic> diagnostics) {
    Map<String, String> familySplits = new HashMap<>();
    Map<String, String> contentSplits = new HashMap<>();
    boolean clean = true;
    for (int i = 0; i < cases.size(); i++) {
      JsonNode item = cases.get(i);
      String split = item.path("split").asText();
      String family = item.path("family_id").asText();
      String content = item.path("content_sha256").asText();
      String oldFamilySplit = familySplits.putIfAbsent(family, split);
      if (oldFamilySplit != null && !oldFamilySplit.equals(split)) {
        diagnostics.add(error(
            "BENCH_SPLIT_FAMILY_LEAKAGE", "/cases/" + i + "/family_id",
            "A family identifier must not cross data splits."));
        clean = false;
      }
      String oldContentSplit = contentSplits.putIfAbsent(content, split);
      if (oldContentSplit != null && !oldContentSplit.equals(split)) {
        diagnostics.add(error(
            "BENCH_SPLIT_CONTENT_LEAKAGE", "/cases/" + i + "/content_sha256",
            "Identical content must not cross data splits."));
        clean = false;
      }
    }
    return clean;
  }

  private boolean validateHoldoutExposure(JsonNode exposures, List<Diagnostic> diagnostics) {
    boolean exposed = false;
    for (int i = 0; i < exposures.size(); i++) {
      JsonNode exposure = exposures.get(i);
      if ("holdout".equals(exposure.path("split").asText())
          && HOLDOUT_DEVELOPMENT_PURPOSES.contains(exposure.path("purpose").asText())) {
        diagnostics.add(policy(
            "BENCH_HOLDOUT_EXPOSED", "/governance/exposures/" + i,
            "Holdout was exposed to development activity."));
        exposed = true;
      }
    }
    return exposed;
  }

  private void validateGovernance(JsonNode governance, List<Diagnostic> diagnostics) {
    JsonNode reviewArray = governance.path("reviews");
    for (int i = 0; i < reviewArray.size(); i++) {
      JsonNode review = reviewArray.get(i);
      String pointer = "/governance/reviews/" + i;
      String mode = review.path("mode").asText();
      String actorType = review.path("actor_type").asText();
      if (mode.startsWith("single_human") || "independent_human_annotation".equals(mode)
          || "human_adjudication".equals(mode)) {
        if (!"human".equals(actorType)) {
          diagnostics.add(error(
              "BENCH_REVIEW_ACTOR_MISMATCH", pointer + "/actor_type",
              "Human review modes require a human actor."));
        }
      }
      if ("single_human_blinded_relabel".equals(mode)) {
        Instant start = instant(review.path("cooldown_started_at").asText());
        Instant end = instant(review.path("cooldown_ended_at").asText());
        Instant submitted = instant(review.path("submitted_at").asText());
        if (start != null && end != null && end.isBefore(start)) {
          diagnostics.add(error(
              "BENCH_REVIEW_COOLDOWN_ORDER", pointer + "/cooldown_ended_at",
              "Review cooldown end must not precede its start."));
        }
        if (end != null && submitted != null && submitted.isBefore(end)) {
          diagnostics.add(error(
              "BENCH_REVIEW_SUBMITTED_EARLY", pointer + "/submitted_at",
              "Blinded review must be submitted after the cooldown."));
        }
      }
    }

    JsonNode disputeArray = governance.path("disputes");
    for (int i = 0; i < disputeArray.size(); i++) {
      JsonNode dispute = disputeArray.get(i);
      if (dispute.path("blocking").asBoolean()
          && Set.of("open", "disputed").contains(dispute.path("status").asText())) {
        diagnostics.add(policy(
            "BENCH_BLOCKING_DISPUTE", "/governance/disputes/" + i,
            "A blocking dispute remains unresolved."));
      }
    }
  }

  private void validateAmendments(
      JsonNode amendments, Map<String, JsonNode> artifacts, List<Diagnostic> diagnostics) {
    for (int i = 0; i < amendments.size(); i++) {
      JsonNode amendment = amendments.get(i);
      String pointer = "/amendments/" + i;
      requireRole(
          artifacts, amendment.path("artifact_id").asText(), "amendment",
          pointer + "/artifact_id", diagnostics);
      if (amendment.path("old_sha256").asText().equals(amendment.path("new_sha256").asText())) {
        diagnostics.add(error(
            "BENCH_AMENDMENT_NO_CHANGE", pointer,
            "Amendment old and new digests must differ."));
      }
      if (HUMAN_APPROVAL_TARGETS.contains(amendment.path("target_type").asText())
          && !"human".equals(amendment.path("approved_by_actor_type").asText())) {
        diagnostics.add(error(
            "BENCH_AMENDMENT_HUMAN_APPROVAL_REQUIRED",
            pointer + "/approved_by_actor_type",
            "Governance-changing amendments require human approval."));
      }
    }
  }

  private void validateCaseAuthorization(JsonNode cases, List<Diagnostic> diagnostics) {
    for (int i = 0; i < cases.size(); i++) {
      JsonNode item = cases.get(i);
      if (item.path("included").asBoolean()
          && Set.of("pending", "rejected").contains(item.path("authorization_status").asText())) {
        diagnostics.add(error(
            "BENCH_CASE_NOT_AUTHORIZED", "/cases/" + i + "/authorization_status",
            "Included cases must have verified or reference-only authorization."));
      }
    }
  }

  private void validateAmendmentRevision(JsonNode root, List<Diagnostic> diagnostics) {
    int revision = root.path("identity").path("revision").asInt();
    int count = root.path("amendments").size();
    if (revision == 1 && count > 0) {
      diagnostics.add(error(
          "BENCH_AMENDMENT_ON_INITIAL_REVISION", "/amendments",
          "Initial revision must not contain amendments."));
    } else if (revision > 1 && count == 0) {
      diagnostics.add(error(
          "BENCH_AMENDMENT_REQUIRED", "/amendments",
          "A later revision must record at least one amendment."));
    }
  }

  private void validateEvaluations(
      JsonNode root, Map<String, JsonNode> artifacts, List<Diagnostic> diagnostics) {
    int revision = root.path("identity").path("revision").asInt();
    JsonNode evaluations = root.path("evaluations");
    JsonNode amendments = root.path("amendments");
    Instant frozenAt = instant(root.path("governance").path("freeze").path("frozen_at").asText());
    Set<String> splits = new HashSet<>();
    root.path("cases").forEach(item -> splits.add(item.path("split").asText()));

    for (int i = 0; i < evaluations.size(); i++) {
      JsonNode evaluation = evaluations.get(i);
      String pointer = "/evaluations/" + i;
      if (evaluation.path("benchmark_revision").asInt() != revision) {
        diagnostics.add(error(
            "BENCH_EVALUATION_REVISION_MISMATCH", pointer + "/benchmark_revision",
            "Evaluation must bind the current manifest revision."));
      }
      if (!splits.contains(evaluation.path("target_split").asText())) {
        diagnostics.add(error(
            "BENCH_EVALUATION_SPLIT_EMPTY", pointer + "/target_split",
            "Evaluation target split has no cases."));
      }
      requireRole(artifacts, evaluation.path("gold_artifact_id").asText(), "gold",
          pointer + "/gold_artifact_id", diagnostics);
      requireRole(artifacts, evaluation.path("matching_policy_artifact_id").asText(),
          "matching_policy", pointer + "/matching_policy_artifact_id", diagnostics);
      requireRole(artifacts, evaluation.path("run_config_artifact_id").asText(), "run_config",
          pointer + "/run_config_artifact_id", diagnostics);
      requireRole(artifacts, evaluation.path("prediction_artifact_id").asText(), "prediction",
          pointer + "/prediction_artifact_id", diagnostics);
      requireRole(artifacts, evaluation.path("result_artifact_id").asText(), "result",
          pointer + "/result_artifact_id", diagnostics);

      if (!evaluation.path("matching_policy_artifact_id").asText()
          .equals(root.path("benchmark").path("matching_policy_artifact_id").asText())) {
        diagnostics.add(error(
            "BENCH_EVALUATION_POLICY_MISMATCH", pointer + "/matching_policy_artifact_id",
            "Evaluation must bind the benchmark matching policy."));
      }

      Instant started = instant(evaluation.path("started_at").asText());
      Instant finished = instant(evaluation.path("finished_at").asText());
      if (started != null && finished != null && finished.isBefore(started)) {
        diagnostics.add(error(
            "BENCH_EVALUATION_TIME_ORDER", pointer + "/finished_at",
            "Evaluation finish must not precede its start."));
      }
      if ("holdout".equals(evaluation.path("target_split").asText())
          && frozenAt != null && started != null && started.isBefore(frozenAt)) {
        diagnostics.add(error(
            "BENCH_EVALUATION_BEFORE_FREEZE", pointer + "/started_at",
            "Holdout evaluation must start after gold is frozen."));
      }
      if (started != null) {
        for (int j = 0; j < amendments.size(); j++) {
          Instant amended = instant(amendments.get(j).path("amended_at").asText());
          if (amended != null && amended.isAfter(started)) {
            diagnostics.add(error(
                "BENCH_EVALUATION_PREDATES_AMENDMENT", pointer + "/started_at",
                "Evaluation predates an amendment in the current revision."));
            break;
          }
        }
      }
    }
  }

  private void validateParent(Path manifestPath, JsonNode identity, List<Diagnostic> diagnostics) {
    int revision = identity.path("revision").asInt();
    if (revision == 1) return;
    if (revision > 1024) {
      diagnostics.add(error(
          "BENCH_PARENT_CHAIN_TOO_DEEP", "/identity/revision",
          "Manifest parent chain exceeds the supported depth."));
      return;
    }

    String manifestId = identity.path("manifest_id").asText();
    Path currentPath = manifestPath.toAbsolutePath().normalize();
    JsonNode currentIdentity = identity;
    Set<Path> seen = new HashSet<>();
    seen.add(currentPath);

    for (int expectedRevision = revision - 1; expectedRevision >= 1; expectedRevision--) {
      JsonNode parent = currentIdentity.path("parent");
      if (!parent.isObject()) {
        diagnostics.add(error(
            "BENCH_PARENT_CHAIN_INCOMPLETE", "/identity/parent",
            "Manifest parent chain must reach revision one."));
        return;
      }

      Path parentPath = artifactValidator.resolveSafe(
          currentPath.getParent(), parent.path("path").asText(), "/identity/parent", diagnostics);
      if (parentPath == null) return;
      if (!seen.add(parentPath)) {
        diagnostics.add(error(
            "BENCH_PARENT_CYCLE", "/identity/parent/path",
            "Manifest parent chain must not contain a cycle."));
        return;
      }
      if (!Files.isRegularFile(parentPath, LinkOption.NOFOLLOW_LINKS)) {
        diagnostics.add(error(
            "BENCH_PARENT_NOT_FOUND", "/identity/parent/path",
            "Parent manifest must be a regular local file."));
        return;
      }

      try {
        if (Files.size(parentPath) > BenchManifestService.MAX_MANIFEST_BYTES) {
          diagnostics.add(error(
              "BENCH_PARENT_TOO_LARGE", "/identity/parent/path",
              "Parent manifest exceeds the configured size limit."));
          return;
        }
        if (!ArtifactIntegrityValidator.sha256(parentPath).equals(parent.path("sha256").asText())) {
          diagnostics.add(error(
              "BENCH_PARENT_HASH_MISMATCH", "/identity/parent/sha256",
              "Parent manifest SHA-256 does not match."));
          return;
        }

        JsonNode parentRoot = mapper.readTree(parentPath.toFile());
        JsonNode parentIdentity = parentRoot.path("identity");
        if (!"openguard-bench-manifest/2.0".equals(parentRoot.path("schema_version").asText())) {
          diagnostics.add(error(
              "BENCH_PARENT_SCHEMA_MISMATCH", "/identity/parent/path",
              "Parent manifest must use the Bench 2.0 contract."));
          return;
        }
        if (!manifestId.equals(parent.path("manifest_id").asText())
            || !manifestId.equals(parentIdentity.path("manifest_id").asText())) {
          diagnostics.add(error(
              "BENCH_PARENT_ID_MISMATCH", "/identity/parent/manifest_id",
              "Parent manifest identifier does not match."));
          return;
        }
        if (parent.path("revision").asInt() != expectedRevision
            || parentIdentity.path("revision").asInt() != expectedRevision) {
          diagnostics.add(error(
              "BENCH_PARENT_REVISION_MISMATCH", "/identity/parent/revision",
              "Parent revision must immediately precede the current revision."));
          return;
        }
        if (expectedRevision == 1 && !parentIdentity.path("parent").isNull()) {
          diagnostics.add(error(
              "BENCH_PARENT_CHAIN_INVALID_ROOT", "/identity/parent/path",
              "Revision one must terminate the parent chain."));
          return;
        }

        currentPath = parentPath;
        currentIdentity = parentIdentity;
      } catch (IOException exception) {
        diagnostics.add(error(
            "BENCH_PARENT_READ_FAILED", "/identity/parent/path",
            "Parent manifest could not be read safely."));
        return;
      }
    }
  }

  private boolean isPolicyFrozen(JsonNode root, Map<String, JsonNode> artifacts) {
    JsonNode freeze = root.path("governance").path("freeze");
    String policyId = root.path("benchmark").path("matching_policy_artifact_id").asText();
    return "frozen".equals(freeze.path("status").asText())
        && contains(freeze.path("artifact_ids"), policyId)
        && hasRole(artifacts.get(policyId), "matching_policy");
  }

  private boolean isGoldFrozen(JsonNode root, Map<String, JsonNode> artifacts) {
    JsonNode freeze = root.path("governance").path("freeze");
    if (!"frozen".equals(freeze.path("status").asText())
        || !"human".equals(freeze.path("frozen_by_actor_type").asText())) return false;
    for (JsonNode item : root.path("cases")) {
      if (item.path("included").asBoolean()) {
        String goldId = item.path("gold_artifact_id").asText();
        if (!contains(freeze.path("artifact_ids"), goldId) || !hasRole(artifacts.get(goldId), "gold")) {
          return false;
        }
      }
    }
    return true;
  }

  private boolean hasNoBlockingDispute(JsonNode disputes) {
    for (JsonNode dispute : disputes) {
      if (dispute.path("blocking").asBoolean()
          && Set.of("open", "disputed").contains(dispute.path("status").asText())) return false;
    }
    return true;
  }

  private boolean hasSingleHumanBlindReview(JsonNode reviews, Set<String> includedCases) {
    if (includedCases.isEmpty()) return false;
    for (JsonNode review : reviews) {
      if ("human".equals(review.path("actor_type").asText())
          && "single_human_blinded_relabel".equals(review.path("mode").asText())
          && !review.path("ai_output_seen").asBoolean()
          && !review.path("system_output_seen").asBoolean()
          && covers(review.path("case_ids"), includedCases)) {
        Instant start = instant(review.path("cooldown_started_at").asText());
        Instant end = instant(review.path("cooldown_ended_at").asText());
        Instant submitted = instant(review.path("submitted_at").asText());
        if (start != null && end != null && submitted != null
            && !end.isBefore(start) && !submitted.isBefore(end)) return true;
      }
    }
    return false;
  }

  private boolean hasIndependentHumanReviews(JsonNode reviews, Set<String> includedCases) {
    if (includedCases.isEmpty()) return false;
    Set<String> reviewers = new HashSet<>();
    for (JsonNode review : reviews) {
      if ("human".equals(review.path("actor_type").asText())
          && "independent_human_annotation".equals(review.path("mode").asText())
          && !review.path("ai_output_seen").asBoolean()
          && !review.path("system_output_seen").asBoolean()
          && covers(review.path("case_ids"), includedCases)) {
        reviewers.add(review.path("reviewer_id").asText());
      }
    }
    return reviewers.size() >= 2;
  }

  private boolean disputesAllowIndependentTier(
      JsonNode governance, Map<String, JsonNode> reviews, Map<String, JsonNode> artifacts) {
    for (JsonNode dispute : governance.path("disputes")) {
      String status = dispute.path("status").asText();
      if ("open".equals(status) || "disputed".equals(status)) return false;
      if ("resolved".equals(status)) {
        if (!hasRole(artifacts.get(dispute.path("resolution_artifact_id").asText()), "resolution")) {
          return false;
        }
        boolean humanAdjudication = false;
        for (JsonNode reviewId : dispute.path("review_ids")) {
          JsonNode review = reviews.get(reviewId.asText());
          if (review != null && "human".equals(review.path("actor_type").asText())
              && "human_adjudication".equals(review.path("mode").asText())) {
            humanAdjudication = true;
          }
        }
        if (!humanAdjudication) return false;
      }
    }
    return true;
  }

  private Set<String> includedCaseIds(JsonNode cases) {
    Set<String> ids = new HashSet<>();
    for (JsonNode item : cases) {
      if (item.path("included").asBoolean()) ids.add(item.path("case_id").asText());
    }
    return ids;
  }

  private boolean covers(JsonNode caseIds, Set<String> expected) {
    Set<String> actual = new HashSet<>();
    caseIds.forEach(id -> actual.add(id.asText()));
    return actual.containsAll(expected);
  }

  private void requireRole(
      Map<String, JsonNode> artifacts, String id, String role, String pointer,
      List<Diagnostic> diagnostics) {
    requireAnyRole(artifacts, id, Set.of(role), pointer, diagnostics);
  }

  private void requireAnyRole(
      Map<String, JsonNode> artifacts, String id, Set<String> roles, String pointer,
      List<Diagnostic> diagnostics) {
    JsonNode artifact = artifacts.get(id);
    if (artifact == null) {
      diagnostics.add(error(
          "BENCH_ARTIFACT_REFERENCE_MISSING", pointer,
          "Referenced artifact does not exist."));
    } else if (!roles.contains(artifact.path("role").asText())) {
      diagnostics.add(error(
          "BENCH_ARTIFACT_ROLE_MISMATCH", pointer,
          "Referenced artifact has an incompatible role."));
    }
  }

  private void requireId(
      Map<String, JsonNode> index, String id, String pointer, String kind,
      List<Diagnostic> diagnostics) {
    if (!index.containsKey(id)) {
      diagnostics.add(error(
          "BENCH_" + kind.toUpperCase() + "_REFERENCE_MISSING", pointer,
          "Referenced " + kind + " does not exist."));
    }
  }

  private static boolean hasRole(JsonNode artifact, String role) {
    return artifact != null && role.equals(artifact.path("role").asText());
  }

  private static boolean contains(JsonNode array, String value) {
    for (JsonNode item : array) if (value.equals(item.asText())) return true;
    return false;
  }

  private static Instant instant(String value) {
    if (value == null || value.isBlank()) return null;
    try {
      return OffsetDateTime.parse(value).toInstant();
    } catch (DateTimeParseException exception) {
      return null;
    }
  }

  private static Diagnostic error(String code, String pointer, String message) {
    return new Diagnostic(code, "error", pointer, message);
  }

  private static Diagnostic policy(String code, String pointer, String message) {
    return new Diagnostic(code, "policy", pointer, message);
  }
}
