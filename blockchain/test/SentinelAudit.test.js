const assert = require("node:assert/strict");
const {ethers, artifacts} = require("hardhat");
describe("SentinelAudit", function () {
  let audit, owner, writer, stranger;
  const key = ethers.sha256(ethers.toUtf8Bytes("opaque test case"));
  const digest = ethers.sha256(ethers.toUtf8Bytes("opaque test digest"));
  beforeEach(async () => {
    [owner, writer, stranger] = await ethers.getSigners();
    audit = await ethers.deployContract("SentinelAudit");
    await audit.waitForDeployment();
  });
  it("deploys executable bytecode", async () => assert.notEqual(await ethers.provider.getCode(await audit.getAddress()), "0x"));
  it("initializes owner and writer", async () => {assert.equal(await audit.owner(), owner.address); assert.equal(await audit.writers(owner.address), true);});
  it("lets an authorized writer anchor", async () => {await audit.authorizeWriter(writer.address, true); await audit.connect(writer).anchorRecord(key, 0, 1, digest); assert.equal(await audit.recordExists(key, 0, 1), true);});
  it("rejects unauthorized writers", async () => {await assert.rejects(audit.connect(stranger).anchorRecord(key, 0, 1, digest), /Unauthorized writer/);});
  it("only owner changes writers", async () => {await assert.rejects(audit.connect(stranger).authorizeWriter(stranger.address, true), /Only owner/);});
  it("revokes a writer", async () => {await audit.authorizeWriter(writer.address, true); await audit.authorizeWriter(writer.address, false); await assert.rejects(audit.connect(writer).anchorRecord(key, 0, 1, digest), /Unauthorized writer/);});
  it("emits exactly the opaque commitment and metadata", async () => {
    const receipt = await (await audit.anchorRecord(key, 0, 1, digest)).wait();
    const event = audit.interface.parseLog(receipt.logs[0]);
    assert.equal(event.name, "AuditAnchored"); assert.equal(event.args.caseKey, key); assert.equal(event.args.digest, digest);
    assert.equal(event.args.submitter, owner.address);
  });
  it("retrieves digest and actual block timestamp", async () => {const r = await (await audit.anchorRecord(key, 0, 1, digest)).wait(); const stored = await audit.getRecord(key, 0, 1); assert.equal(stored.digest, digest); assert.equal(stored.timestamp, BigInt((await ethers.provider.getBlock(r.blockNumber)).timestamp));});
  it("cannot overwrite or double anchor", async () => {await audit.anchorRecord(key, 0, 1, digest); await assert.rejects(audit.anchorRecord(key, 0, 1, digest), /Already anchored/);});
  it("versions coexist", async () => {await audit.anchorRecord(key, 0, 1, digest); await audit.anchorRecord(key, 0, 2, key); assert.equal((await audit.getRecord(key, 0, 1)).digest, digest); assert.equal((await audit.getRecord(key, 0, 2)).digest, key);});
  it("keeps officer and screening entries distinct", async () => {await audit.anchorRecord(key, 0, 1, digest); await audit.anchorRecord(key, 1, 1, key); assert.equal((await audit.getRecord(key, 0, 1)).digest, digest); assert.equal((await audit.getRecord(key, 1, 1)).digest, key);});
  it("exposes no PII or arbitrary string arguments", async () => {const abi=(await artifacts.readArtifact("SentinelAudit")).abi; const fn=abi.find(x=>x.name === "anchorRecord"); assert.deepEqual(fn.inputs.map(x=>x.type), ["bytes32","uint8","uint256","bytes32"]); assert(!JSON.stringify(abi).match(/full_name|dateOfBirth|image|embedding|notes|passport/i));});
});
