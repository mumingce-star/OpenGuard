package dev.openguard.scan;

import java.nio.file.Files;
import java.nio.file.Path;

/** CLI for an already checked-out, explicitly trusted repository. */
public final class RealRepositoryScan {
    private RealRepositoryScan() {}

    public static void main(String[] arguments) throws Exception {
        if (arguments.length != 4 || !"--trusted-checkout".equals(arguments[0])) {
            throw new IllegalArgumentException("usage: --trusted-checkout <directory> <source> <output-directory>");
        }
        ScanResult result = new RepositoryScanner().scanTrustedCheckout(Path.of(arguments[1]), arguments[2], "trusted-checkout");
        Path output = Path.of(arguments[3]);
        Files.createDirectories(output);
        Files.writeString(output.resolve("scan-result.json"), StructuredReports.json(result));
        Files.writeString(output.resolve("resource-inventory.csv"), StructuredReports.csv(result));
        Files.writeString(output.resolve("report.html"), StructuredReports.html(result));
        System.out.printf("scan_id=%s status=%s components=%d licenses=%d findings=%d%n", result.scanId(), result.status(),
                result.components().size(), result.licenses().size(), result.findings().size());
    }
}
