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
        Path checkout = Path.of(arguments[1]).toRealPath();
        Path output = Path.of(arguments[3]).toAbsolutePath().normalize();
        if (output.startsWith(checkout) || Files.exists(output)) {
            throw new IllegalArgumentException("output_must_be_new_and_outside_checkout");
        }
        Files.createDirectories(output.getParent());
        if (output.getParent().toRealPath().startsWith(checkout)) {
            throw new IllegalArgumentException("output_must_be_outside_checkout");
        }
        ScanResult result = new RepositoryScanner().scanTrustedCheckout(Path.of(arguments[1]), arguments[2], "trusted-checkout");
        Files.createDirectory(output);
        Files.writeString(output.resolve("scan-result.json"), StructuredReports.json(result), java.nio.file.StandardOpenOption.CREATE_NEW);
        Files.writeString(output.resolve("resource-inventory.csv"), StructuredReports.csv(result), java.nio.file.StandardOpenOption.CREATE_NEW);
        Files.writeString(output.resolve("report.html"), StructuredReports.html(result), java.nio.file.StandardOpenOption.CREATE_NEW);
        System.out.printf("scan_id=%s status=%s components=%d licenses=%d findings=%d%n", result.scanId(), result.status(),
                result.components().size(), result.licenses().size(), result.findings().size());
    }
}
