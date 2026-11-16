package dev.openguard.bench;

import com.fasterxml.jackson.annotation.JsonPropertyOrder;
import java.util.List;

@JsonPropertyOrder({
  "contract_version",
  "valid",
  "manifest_sha256",
  "derived_tier",
  "requested_tiers",
  "diagnostics"
})
public record ValidationReport(
    String contractVersion,
    boolean valid,
    String manifestSha256,
    String derivedTier,
    List<String> requestedTiers,
    List<Diagnostic> diagnostics) {
  public static final String CONTRACT_VERSION = "openguard-bench-validation-report/1.0";
}
