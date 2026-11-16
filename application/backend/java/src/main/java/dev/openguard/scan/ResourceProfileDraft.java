package dev.openguard.scan;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.util.List;
import java.util.Map;

/** Provider-neutral, offline-only AI resource profile candidate. */
public record ResourceProfileDraft(
        String schemaVersion, String draftId, String resourceKind, String provider,
        String providerResourceId, String canonicalUrl, String revision, String visibility,
        String accessGate, String declaredLicense, Map<String, List<EvidenceRef>> fieldEvidence,
        List<String> diagnostics) {
    /** String timestamp keeps JSON output dependency-free and RFC 3339 stable. */
    public record EvidenceRef(String fixturePath, String fixtureSha256, String jsonPointer, String observedAt) {}

    public record P0Candidate(String assetType, String name, String provider, String version,
            String sourceUrl, String licenseExpressionId, String authorizationStatus, List<EvidenceRef> evidence) {}

    public static ResourceProfileDraft fromHuggingFace(JsonNode root, String kind, String fixturePath,
            String fixtureSha256, Instant observedAt) {
        if (!root.isObject() || !(kind.equals("model") || kind.equals("dataset"))
                || !fixturePath.matches("[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*")
                || !fixtureSha256.matches("[0-9a-f]{64}")) throw new IllegalArgumentException("invalid_fixture");
        JsonNode idNode = root.get("id");
        if (idNode == null || !idNode.isTextual() || !idNode.asText().matches("[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}"))
            throw new IllegalArgumentException("missing_required_id");
        String id = idNode.asText();
        var diagnostics = new java.util.ArrayList<String>();
        var evidence = new java.util.TreeMap<String, List<EvidenceRef>>();
        java.util.function.Function<String, EvidenceRef> ref = pointer -> new EvidenceRef(fixturePath, fixtureSha256, pointer, observedAt.toString());
        evidence.put("identity.provider_resource_id", List.of(ref.apply("/id")));
        evidence.put("identity.canonical_url", List.of(ref.apply("/id")));
        String revision = text(root, "sha");
        if (revision != null && !revision.matches("[0-9a-f]{40}(?:[0-9a-f]{24})?")) { diagnostics.add("invalid_revision"); revision = null; }
        else if (revision != null) evidence.put("identity.revision", List.of(ref.apply("/sha")));
        String visibility = root.path("private").isBoolean() ? (root.path("private").asBoolean() ? "private" : "public") : "unknown";
        if (!visibility.equals("unknown")) evidence.put("lifecycle.visibility", List.of(ref.apply("/private")));
        String gate = "unknown";
        if (root.has("gated")) { if (root.path("gated").isBoolean()) { gate = root.path("gated").asBoolean() ? "gated" : "ungated"; evidence.put("lifecycle.access_gate", List.of(ref.apply("/gated"))); } else diagnostics.add("unsupported_gate_value"); }
        String cardLicense = root.path("cardData").path("license").isTextual() ? root.path("cardData").path("license").asText() : null;
        String topLicense = text(root, "license"); String license = cardLicense != null ? cardLicense : topLicense;
        if (cardLicense != null && topLicense != null && !cardLicense.equals(topLicense)) { license = null; diagnostics.add("conflicting_declared_license"); evidence.put("declared_metadata.license_text", List.of(ref.apply("/license"), ref.apply("/cardData/license"))); }
        else if (license != null) evidence.put("declared_metadata.license_text", List.of(ref.apply(cardLicense != null ? "/cardData/license" : "/license")));
        String url = kind.equals("dataset") ? "https://huggingface.co/datasets/" + id : "https://huggingface.co/" + id;
        String draftId = "rpd_" + java.util.UUID.nameUUIDFromBytes(("resource-profile-draft/0.1|" + kind + "|huggingface|" + id + "|" + fixtureSha256).getBytes(java.nio.charset.StandardCharsets.UTF_8));
        return new ResourceProfileDraft("resource-profile-draft/0.1", draftId, kind, "huggingface", id, url, revision, visibility, gate, license, evidence, List.copyOf(diagnostics));
    }
    private static String text(JsonNode root, String field) { return root.path(field).isTextual() ? root.path(field).asText() : null; }
    public P0Candidate toPendingP0Candidate() {
        return new P0Candidate(resourceKind, providerResourceId, provider, revision, canonicalUrl, null, "pending",
                fieldEvidence.values().stream().flatMap(List::stream).distinct().toList());
    }
}
