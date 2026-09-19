package dev.openguard.bench;

public record ValidationOutcome(int exitCode, ValidationReport report) {}
