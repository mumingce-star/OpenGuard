package dev.openguard.scan;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Bounded, read-only repository scanner. It deliberately never runs source code,
 * installs dependencies, reads outside the supplied checkout, or infers legal clearance.
 */
public final class RepositoryScanner {
    private static final int MAX_FILES = 4_000;
    private static final long MAX_FILE_BYTES = 512 * 1024;
    private static final Pattern PYTHON_REQUIREMENT = Pattern.compile(
            "^\\s*([A-Za-z0-9_.-]+)(?:\\s*(?:===|==|>=|<=|~=|!=|>|<)\\s*([A-Za-z0-9_.+!-]+))?.*$",
            Pattern.MULTILINE);
    private static final Pattern QUOTED_REQUIREMENT = Pattern.compile(
            "[\\\"']([A-Za-z0-9_.-]+)(?:\\s*(?:===|==|>=|<=|~=|!=|>|<)\\s*([A-Za-z0-9_.+!-]+))?[\\\"']");
    private static final Pattern AI_URL = Pattern.compile(
            "https://(?:huggingface[.]co|www[.]kaggle[.]com/datasets|modelscope[.]cn)/[^\\s)\\]}>\\\"']+",
            Pattern.CASE_INSENSITIVE);
    private static final ObjectMapper JSON = new ObjectMapper();

    public ScanResult scanTrustedCheckout(Path checkout, String source, String revision) throws IOException {
        if (!Files.isDirectory(checkout)) {
            throw new IllegalArgumentException("trusted_checkout_must_be_directory");
        }
        Path normalizedRoot = checkout.toRealPath();
        var components = new ArrayList<ScanResult.Component>();
        var licenses = new ArrayList<ScanResult.License>();
        var assets = new ArrayList<ScanResult.AiAsset>();
        var evidence = new ArrayList<ScanResult.Evidence>();
        var diagnostics = new ArrayList<String>();
        List<Path> paths;
        try (var walked = Files.walk(normalizedRoot)) {
            paths = walked.filter(Files::isRegularFile)
                    .filter(path -> !path.startsWith(normalizedRoot.resolve(".git")))
                    .sorted(Comparator.comparing(path -> normalizedRoot.relativize(path).toString()))
                    .limit(MAX_FILES + 1).toList();
        }
        if (paths.size() > MAX_FILES) {
            throw new IllegalArgumentException("repository_file_limit_exceeded");
        }
        for (Path path : paths) {
            String relative = normalizedRoot.relativize(path).toString().replace('\\', '/');
            if (Files.size(path) > MAX_FILE_BYTES) {
                diagnostics.add("skipped_oversize:" + relative);
                continue;
            }
            if (relative.equals("pyproject.toml") || relative.matches("(?:.*/)?requirements[^/]*[.]txt")) {
                parsePythonManifest(path, relative, components, evidence, diagnostics);
            } else if (relative.equals("package.json")) {
                parsePackageManifest(path, relative, components, evidence, diagnostics);
            }
            if (relative.toLowerCase(Locale.ROOT).matches("(?:.*/)?(?:license|copying|notice)(?:[.].*)?")) {
                parseLicense(path, relative, licenses, evidence, diagnostics);
            }
            if (isTextCandidate(relative)) {
                parseAiReferences(path, relative, assets, evidence, diagnostics);
            }
        }
        List<ScanResult.Finding> findings = findings(licenses, assets);
        return new ScanResult("0.1.1", "scn_" + UUID.randomUUID(), "completed", source, revision,
                Instant.now().toString(), List.copyOf(components), List.copyOf(licenses), List.copyOf(assets),
                List.copyOf(evidence), findings, List.copyOf(diagnostics));
    }

    private static void parsePythonManifest(Path path, String relative, List<ScanResult.Component> components,
            List<ScanResult.Evidence> evidence, List<String> diagnostics) {
        try {
            String content = Files.readString(path, StandardCharsets.UTF_8);
            String declarations = relative.equals("pyproject.toml") ? dependencyArray(content) : content;
            Matcher matcher = (relative.equals("pyproject.toml") ? QUOTED_REQUIREMENT : PYTHON_REQUIREMENT).matcher(declarations);
            while (matcher.find()) {
                String name = matcher.group(1);
                if (name.equalsIgnoreCase("dependencies") || name.equalsIgnoreCase("project")) {
                    continue;
                }
                String version = matcher.group(2) == null ? "unknown" : matcher.group(2);
                components.add(new ScanResult.Component(name, version, "pypi", relative));
                evidence.add(new ScanResult.Evidence("manifest_field", relative, matcher.group().strip()));
            }
        } catch (IOException exception) {
            diagnostics.add("python_manifest_unreadable:" + relative);
        }
    }

    private static String dependencyArray(String content) {
        int key = content.indexOf("dependencies");
        if (key < 0) return "";
        int open = content.indexOf('[', key);
        int close = open < 0 ? -1 : content.indexOf(']', open);
        return open < 0 || close < 0 ? "" : content.substring(open + 1, close);
    }

    private static void parsePackageManifest(Path path, String relative, List<ScanResult.Component> components,
            List<ScanResult.Evidence> evidence, List<String> diagnostics) {
        try {
            JsonNode root = JSON.readTree(path.toFile());
            for (String section : List.of("dependencies", "devDependencies")) {
                JsonNode dependencies = root.path(section);
                if (!dependencies.isObject()) continue;
                dependencies.fields().forEachRemaining(entry -> {
                    String version = entry.getValue().isTextual() ? entry.getValue().asText() : "unknown";
                    components.add(new ScanResult.Component(entry.getKey(), version, "npm", relative));
                    evidence.add(new ScanResult.Evidence("manifest_field", relative, section + "." + entry.getKey()));
                });
            }
        } catch (IOException exception) {
            diagnostics.add("package_manifest_unreadable:" + relative);
        }
    }

    private static void parseLicense(Path path, String relative, List<ScanResult.License> licenses,
            List<ScanResult.Evidence> evidence, List<String> diagnostics) {
        try {
            String text = Files.readString(path, StandardCharsets.UTF_8);
            String excerpt = text.substring(0, Math.min(text.length(), 4_096));
            String upper = excerpt.toUpperCase(Locale.ROOT);
            String spdx = upper.contains("MIT LICENSE") ? "MIT"
                    : upper.contains("APACHE LICENSE") ? "Apache-2.0"
                    : upper.contains("BSD-3-CLAUSE") || (upper.contains("REDISTRIBUTION AND USE") && upper.contains("NEITHER THE NAME")) ? "BSD-3-Clause"
                    : upper.contains("GNU GENERAL PUBLIC LICENSE") ? "GPL-3.0-or-later" : "NOASSERTION";
            licenses.add(new ScanResult.License(spdx, relative, "pending"));
            evidence.add(new ScanResult.Evidence("license_text", relative, excerpt.lines().findFirst().orElse("")));
        } catch (IOException exception) {
            diagnostics.add("license_unreadable:" + relative);
        }
    }

    private static void parseAiReferences(Path path, String relative, List<ScanResult.AiAsset> assets,
            List<ScanResult.Evidence> evidence, List<String> diagnostics) {
        try {
            Matcher matcher = AI_URL.matcher(Files.readString(path, StandardCharsets.UTF_8));
            while (matcher.find()) {
                String url = matcher.group();
                assets.add(new ScanResult.AiAsset(url, "referenced_resource", relative));
                evidence.add(new ScanResult.Evidence("url", relative, url));
            }
        } catch (IOException exception) {
            diagnostics.add("text_candidate_unreadable:" + relative);
        }
    }

    private static List<ScanResult.Finding> findings(List<ScanResult.License> licenses, List<ScanResult.AiAsset> assets) {
        var findings = new ArrayList<ScanResult.Finding>();
        for (var license : licenses) findings.add(new ScanResult.Finding("license.notice.review", "review_required", "low",
                license.spdxId(), license.evidencePath(), "License text was found; distribution context and obligations require human review."));
        for (var asset : assets) findings.add(new ScanResult.Finding("ai.asset.authorization.review", "review_required", "medium",
                asset.url(), asset.evidencePath(), "AI resource reference found; authorization and intended use require human review."));
        return List.copyOf(findings);
    }

    private static boolean isTextCandidate(String path) {
        return path.endsWith(".md") || path.endsWith(".txt") || path.endsWith(".py") || path.endsWith(".json") || path.endsWith(".toml");
    }
}
