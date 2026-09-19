package dev.openguard.bench;

import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.StreamReadFeature;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public final class BenchManifestService {
  public static final long MAX_MANIFEST_BYTES = 2L * 1024L * 1024L;

  private final ObjectMapper mapper;
  private final JsonSchemaManifestValidator schemaValidator;
  private final ArtifactIntegrityValidator artifactValidator;
  private final BenchSemanticValidator semanticValidator;

  public BenchManifestService() {
    JsonFactory jsonFactory =
        JsonFactory.builder().enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION).build();
    this.mapper = new ObjectMapper(jsonFactory);
    this.mapper.enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
    this.mapper.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
    this.schemaValidator = new JsonSchemaManifestValidator();
    this.artifactValidator = new ArtifactIntegrityValidator();
    this.semanticValidator = new BenchSemanticValidator(mapper, artifactValidator);
  }

  public ValidationOutcome validate(Path manifestPath) {
    if (manifestPath == null
        || !Files.isRegularFile(manifestPath, LinkOption.NOFOLLOW_LINKS)
        || Files.isSymbolicLink(manifestPath)) {
      return inputFailure(
          "BENCH_INPUT_NOT_REGULAR_FILE", "Manifest must be a regular local file.");
    }

    byte[] bytes;
    try {
      long size = Files.size(manifestPath);
      if (size > MAX_MANIFEST_BYTES) {
        return inputFailure(
            "BENCH_INPUT_TOO_LARGE", "Manifest exceeds the configured size limit.");
      }
      bytes = Files.readAllBytes(manifestPath);
    } catch (IOException exception) {
      return inputFailure("BENCH_INPUT_READ_FAILED", "Manifest could not be read safely.");
    }

    String manifestHash = sha256(bytes);
    String text;
    try {
      text =
          StandardCharsets.UTF_8
              .newDecoder()
              .onMalformedInput(CodingErrorAction.REPORT)
              .onUnmappableCharacter(CodingErrorAction.REPORT)
              .decode(ByteBuffer.wrap(bytes))
              .toString();
    } catch (CharacterCodingException exception) {
      return inputFailure(
          "BENCH_INPUT_UTF8_INVALID", "Manifest must be valid UTF-8.", manifestHash);
    }

    JsonNode root;
    try {
      root = mapper.readTree(text);
      if (root == null) {
        return inputFailure(
            "BENCH_INPUT_JSON_INVALID", "Manifest must contain one JSON value.", manifestHash);
      }
    } catch (JsonProcessingException exception) {
      return inputFailure(
          "BENCH_INPUT_JSON_INVALID", "Manifest must be valid JSON.", manifestHash);
    }

    List<Diagnostic> diagnostics = new ArrayList<>(schemaValidator.validate(root));
    if (!diagnostics.isEmpty()) {
      return outcome(1, false, manifestHash, null, List.of(), diagnostics);
    }

    diagnostics.addAll(artifactValidator.validate(manifestPath, root.path("artifacts")));
    BenchSemanticValidator.Result semantic = semanticValidator.validate(manifestPath, root);
    diagnostics.addAll(semantic.diagnostics());

    List<String> requestedTiers = requestedTiers(root);
    boolean hasErrors = diagnostics.stream().anyMatch(d -> "error".equals(d.severity()));
    if (hasErrors) {
      return outcome(
          1,
          false,
          manifestHash,
          semantic.derivedTier().contractName(),
          requestedTiers,
          diagnostics);
    }

    boolean tierRejected = false;
    JsonNode evaluations = root.path("evaluations");
    for (int i = 0; i < evaluations.size(); i++) {
      MetricTier requested =
          MetricTier.fromContractName(evaluations.get(i).path("requested_tier").asText());
      if (!semantic.derivedTier().satisfies(requested)) {
        diagnostics.add(
            new Diagnostic(
                "BENCH_TIER_NOT_MET",
                "policy",
                "/evaluations/" + i + "/requested_tier",
                "Requested metric tier exceeds the derived tier."));
        tierRejected = true;
      }
    }

    return outcome(
        tierRejected ? 3 : 0,
        true,
        manifestHash,
        semantic.derivedTier().contractName(),
        requestedTiers,
        diagnostics);
  }

  ObjectMapper mapper() {
    return mapper;
  }

  private List<String> requestedTiers(JsonNode root) {
    Set<String> tiers = new LinkedHashSet<>();
    root.path("evaluations").forEach(item -> tiers.add(item.path("requested_tier").asText()));
    return List.copyOf(tiers);
  }

  private ValidationOutcome inputFailure(String code, String message) {
    return inputFailure(code, message, null);
  }

  private ValidationOutcome inputFailure(String code, String message, String manifestHash) {
    return outcome(
        2,
        false,
        manifestHash,
        null,
        List.of(),
        List.of(new Diagnostic(code, "error", "", message)));
  }

  private ValidationOutcome outcome(
      int exitCode,
      boolean valid,
      String manifestHash,
      String derivedTier,
      List<String> requestedTiers,
      List<Diagnostic> diagnostics) {
    List<Diagnostic> sorted = diagnostics.stream().distinct().sorted().toList();
    ValidationReport report =
        new ValidationReport(
            ValidationReport.CONTRACT_VERSION,
            valid,
            manifestHash,
            derivedTier,
            List.copyOf(requestedTiers),
            sorted);
    return new ValidationOutcome(exitCode, report);
  }

  private static String sha256(byte[] bytes) {
    try {
      return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
    } catch (NoSuchAlgorithmException impossible) {
      throw new IllegalStateException("SHA-256 is unavailable", impossible);
    }
  }
}
