import Workflow.App.Main
import Workflow.Tests.Runner
import Candidates.Catalogue

private def help : String :=
  "Plutus UPV: Universal Property Verifier\n" ++
  "Formal verification of universal properties against compiled Plutus validators.\n\n" ++
  "Usage:\n" ++
  "  plutus-upv run BLUEPRINT VALIDATOR [--check PROPERTY_ID] [--timeout-ms MILLISECONDS]\n" ++
  "  plutus-upv test\n" ++
  "  plutus-upv --help\n\n" ++
  "test runs all workflow suites with verbose output and retained logs.\n"

def main (args : List String) : IO UInt32 := do
  match args with
  | [] | ["--help"] | ["help"] => IO.print help; return 0
  | ["run", "--help"] | ["test", "--help"] => IO.print help; return 0
  | "run" :: rest => Workflow.Main.run Candidates.Catalogue.loadProvider rest
  | ["test"] => Workflow.Tests.Runner.run
  | _ => IO.eprint help; return 2
