import { MeshTxBuilder } from "@meshsdk/core";
import { describe, expect, it, vi } from "vitest";
import type { VestingDatum } from "../../src/vesting/types";
import {
  buildCancelTx,
  buildClaimTx,
  vestingScriptAddress,
} from "../../src/vesting/vesting";

const address = vestingScriptAddress();
const walletAddress =
  "addr_test1qz2fxv2umyhttkxyxp8x0dlpdt3k6cwng5pxj3jhsydzer3n0d3vllmyqwsx5wktcd8cc3sq835lu7drv2xwl2wywfgs68faae";
const signer = { kind: "key", hash: "ab".repeat(28) } as const;
const datum: VestingDatum = {
  beneficiary: signer,
  locker: signer,
  vesting: [{ policyId: "", assetName: "", total: 6_000_000n }],
  startTime: 1000,
  endTime: 2000,
  recoveryTime: 2500,
};

function fixture() {
  const txBuilder = new MeshTxBuilder();
  vi.spyOn(txBuilder, "complete").mockResolvedValue("unsigned");
  const amount = [{ unit: "lovelace", quantity: "6000000" }];
  return {
    txBuilder,
    datum,
    customSlotConfig: {
      zeroTime: 1000,
      zeroSlot: 0,
      slotLength: 100,
      startEpoch: 0,
      epochLength: 100,
    },
    vestingUtxo: {
      input: { txHash: "ab".repeat(32), outputIndex: 0 },
      output: { address, amount },
    },
    collateralUtxo: {
      input: { txHash: "cd".repeat(32), outputIndex: 0 },
      output: { address: walletAddress, amount },
    },
    beneficiaryAddress: walletAddress,
    lockerAddress: walletAddress,
    utxos: [],
  };
}

describe("vesting builder validity bounds", () => {
  it("keeps the remainder at the start of the enclosing slot", async () => {
    const params = fixture();
    const output = vi.spyOn(params.txBuilder, "txOut");
    const lowerBound = vi.spyOn(params.txBuilder, "invalidBefore");
    await buildClaimTx({ ...params, now: 1590 });
    expect(lowerBound).toHaveBeenCalledWith(5);
    expect(output).toHaveBeenCalledWith(address, [
      { unit: "lovelace", quantity: "3000000" },
    ]);
  });

  it("continues an empty bundle until the end of vesting", async () => {
    const params = fixture();
    const output = vi.spyOn(params.txBuilder, "txOut");
    await buildClaimTx({
      ...params,
      datum: { ...datum, vesting: [] },
      now: 1590,
    });
    expect(output).toHaveBeenCalledWith(address, [
      { unit: "lovelace", quantity: "1500000" },
    ]);
  });

  it("fully releases the bundle when the slot starts at endTime", async () => {
    const params = fixture();
    const output = vi.spyOn(params.txBuilder, "txOut");
    await buildClaimTx({ ...params, now: datum.endTime });
    expect(output).not.toHaveBeenCalled();
  });

  it.each([2500, 2501])(
    "rejects a Cancel at %i when the slot starts at recoveryTime",
    async (now) => {
      await expect(buildCancelTx({ ...fixture(), now })).rejects.toThrow(
        /recoveryTime/,
      );
    },
  );

  it("accepts the first Cancel slot starting after recoveryTime", async () => {
    const params = fixture();
    const lowerBound = vi.spyOn(params.txBuilder, "invalidBefore");
    await buildCancelTx({ ...params, now: 2600 });
    expect(lowerBound).toHaveBeenCalledWith(16);
  });
});
