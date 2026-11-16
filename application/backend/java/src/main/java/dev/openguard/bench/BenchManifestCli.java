package dev.openguard.bench;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import java.io.PrintStream;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;
import java.util.List;

public final class BenchManifestCli {
  private BenchManifestCli() {}

  public static void main(String[] args) {
    System.exit(run(args, System.out, System.err));
  }

  public static int run(String[] args, PrintStream stdout, PrintStream stderr) {
    ValidationOutcome outcome;
    if (args == null || args.length != 2 || !"validate".equals(args[0])) {
      outcome =
          new ValidationOutcome(
              2,
              new ValidationReport(
                  ValidationReport.CONTRACT_VERSION,
                  false,
                  null,
                  null,
                  List.of(),
                  List.of(
                      new Diagnostic(
                          "BENCH_CLI_USAGE",
                          "error",
                          "",
                          "Usage: BenchManifestCli validate <manifest.json>."))));
    } else {
      try {
        outcome = new BenchManifestService().validate(Path.of(args[1]));
      } catch (InvalidPathException exception) {
        outcome =
            new ValidationOutcome(
                2,
                new ValidationReport(
                    ValidationReport.CONTRACT_VERSION,
                    false,
                    null,
                    null,
                    List.of(),
                    List.of(
                        new Diagnostic(
                            "BENCH_INPUT_PATH_INVALID",
                            "error",
                            "",
                            "Manifest path is invalid."))));
      }
    }

    try {
      ObjectMapper mapper = new ObjectMapper();
      mapper.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
      stdout.println(mapper.writeValueAsString(outcome.report()));
      stdout.flush();
    } catch (Exception exception) {
      stderr.println("Bench validator could not serialize its report.");
      stderr.flush();
      return 2;
    }
    return outcome.exitCode();
  }
}
