import Workflow.Main
import Candidates.Catalogue

def main (args : List String) : IO UInt32 :=
  Workflow.Main.run Candidates.Catalogue.selectProvider args
