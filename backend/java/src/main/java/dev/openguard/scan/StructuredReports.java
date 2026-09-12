package dev.openguard.scan;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;

/** Deterministic JSON, CSV and HTML renderers. Data is escaped at the output boundary. */
public final class StructuredReports {
    private static final ObjectMapper JSON = new ObjectMapper()
            .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);

    private StructuredReports() {}

    public static String json(ScanResult result) {
        try {
            return JSON.writerWithDefaultPrettyPrinter().writeValueAsString(result);
        } catch (Exception exception) {
            throw new IllegalStateException("report_json_render_failed", exception);
        }
    }

    public static String csv(ScanResult result) {
        StringBuilder output = new StringBuilder("kind,name,version,ecosystem,evidence_path\n");
        for (var component : result.components()) {
            output.append("component,").append(csv(component.name())).append(',')
                    .append(csv(component.version())).append(',').append(csv(component.ecosystem()))
                    .append(',').append(csv(component.evidencePath())).append('\n');
        }
        for (var license : result.licenses()) {
            output.append("license,").append(csv(license.spdxId())).append(",,,")
                    .append(csv(license.evidencePath())).append('\n');
        }
        for (var asset : result.aiAssets()) {
            output.append("ai_asset,").append(csv(asset.url())).append(",,,")
                    .append(csv(asset.evidencePath())).append('\n');
        }
        return output.toString();
    }

    public static String html(ScanResult result) {
        String items = result.findings().stream().map(finding -> "<li>" + escape(finding.severity())
                + ": " + escape(finding.message()) + " (" + escape(finding.evidencePath()) + ")</li>")
                .reduce("", String::concat);
        return "<!doctype html><html><head><meta charset=\"utf-8\"><title>OpenGuard scan report</title>"
                + "</head><body><h1>OpenGuard scan report</h1><p>Status: " + escape(result.status())
                + "</p><p>Source: " + escape(result.source()) + "</p><h2>Findings</h2><ul>" + items
                + "</ul></body></html>";
    }

    private static String csv(String value) {
        return '\"' + (value == null ? "" : value.replace("\"", "\"\"")) + '\"';
    }

    private static String escape(String value) {
        return (value == null ? "" : value).replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace("\"", "&quot;");
    }
}
