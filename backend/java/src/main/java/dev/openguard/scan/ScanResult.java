package dev.openguard.scan;

import java.util.List;

/** Immutable, evidence-first result shared by the Java scanner and report renderers. */
public record ScanResult(
        String contractVersion,
        String scanId,
        String status,
        String source,
        String revision,
        String createdAt,
        List<Component> components,
        List<License> licenses,
        List<AiAsset> aiAssets,
        List<Evidence> evidence,
        List<Finding> findings,
        List<String> diagnostics) {
    public record Component(String name, String version, String ecosystem, String evidencePath) {}
    public record License(String spdxId, String evidencePath, String verificationStatus) {}
    public record AiAsset(String url, String assetType, String evidencePath) {}
    public record Evidence(String kind, String path, String excerpt) {}
    public record Finding(String ruleId, String outcome, String severity, String resource, String evidencePath, String message) {}
}
