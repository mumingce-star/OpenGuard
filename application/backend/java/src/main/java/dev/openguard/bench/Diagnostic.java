package dev.openguard.bench;

import com.fasterxml.jackson.annotation.JsonPropertyOrder;

@JsonPropertyOrder({"code", "severity", "json_pointer", "message"})
public record Diagnostic(String code, String severity, String jsonPointer, String message)
    implements Comparable<Diagnostic> {
  @Override
  public int compareTo(Diagnostic other) {
    int severityOrder = Integer.compare(rank(severity), rank(other.severity));
    if (severityOrder != 0) return severityOrder;
    int codeOrder = code.compareTo(other.code);
    if (codeOrder != 0) return codeOrder;
    int pointerOrder = jsonPointer.compareTo(other.jsonPointer);
    if (pointerOrder != 0) return pointerOrder;
    return message.compareTo(other.message);
  }

  private static int rank(String value) {
    return switch (value) {
      case "error" -> 0;
      case "policy" -> 1;
      case "warning" -> 2;
      default -> 3;
    };
  }
}
