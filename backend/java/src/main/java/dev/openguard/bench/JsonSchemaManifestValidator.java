package dev.openguard.bench;

import com.fasterxml.jackson.databind.JsonNode;
import com.networknt.schema.Error;
import com.networknt.schema.Schema;
import com.networknt.schema.SchemaLocation;
import com.networknt.schema.SchemaRegistry;
import com.networknt.schema.SchemaRegistryConfig;
import com.networknt.schema.dialect.Dialects;
import java.util.List;
import java.util.Locale;

final class JsonSchemaManifestValidator {
  private static final String SCHEMA_LOCATION = "classpath:schema/bench/v2/manifest.schema.json";
  private final Schema schema;

  JsonSchemaManifestValidator() {
    SchemaRegistryConfig config =
        SchemaRegistryConfig.builder().formatAssertionsEnabled(true).failFast(false).build();
    SchemaRegistry registry =
        SchemaRegistry.withDialect(
            Dialects.getDraft202012(), builder -> builder.schemaRegistryConfig(config));
    this.schema = registry.getSchema(SchemaLocation.of(SCHEMA_LOCATION));
    this.schema.initializeValidators();
  }

  List<Diagnostic> validate(JsonNode manifest) {
    return schema.validate(manifest).stream().map(JsonSchemaManifestValidator::map).sorted().toList();
  }

  private static Diagnostic map(Error error) {
    String keyword = error.getKeyword() == null ? "unknown" : error.getKeyword();
    String normalized = keyword.replaceAll("[^A-Za-z0-9]+", "_").toUpperCase(Locale.ROOT);
    String pointer = error.getInstanceLocation() == null ? "" : error.getInstanceLocation().toString();
    return new Diagnostic(
        "BENCH_SCHEMA_" + normalized,
        "error",
        pointer,
        "Manifest violates JSON Schema keyword '" + keyword + "'.");
  }
}
