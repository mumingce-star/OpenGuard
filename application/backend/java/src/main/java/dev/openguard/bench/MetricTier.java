package dev.openguard.bench;

import java.util.Locale;

public enum MetricTier {
  SMOKE,
  DEVELOPMENT,
  REPORTABLE_SINGLE_HUMAN,
  REPORTABLE_INDEPENDENT;

  public String contractName() {
    return name().toLowerCase(Locale.ROOT);
  }

  public boolean satisfies(MetricTier requested) {
    return ordinal() >= requested.ordinal();
  }

  public static MetricTier fromContractName(String value) {
    return MetricTier.valueOf(value.toUpperCase(Locale.ROOT));
  }
}
