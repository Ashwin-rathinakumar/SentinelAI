// Local development only: create a funded writer and secret without printing either.
const {ethers} = require("hardhat");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const dotenv = require("dotenv");
async function main() {
  if (Number((await ethers.provider.getNetwork()).chainId) !== 31337) throw new Error("Local chain required");
  const output = path.join(__dirname, "../../backend/.env.audit-local");
  const previous = fs.existsSync(output) ? dotenv.parse(fs.readFileSync(output)) : {};
  const deployment = JSON.parse(fs.readFileSync(path.join(__dirname, "../deployments/local.json"), "utf8"));
  const [owner] = await ethers.getSigners();
  if (deployment.chainId !== 31337 || await ethers.provider.getCode(deployment.address) === "0x") {
    throw new Error("Deploy the local audit contract first");
  }
  const writer = previous.BLOCKCHAIN_WRITER_PRIVATE_KEY
    ? new ethers.Wallet(previous.BLOCKCHAIN_WRITER_PRIVATE_KEY) : ethers.Wallet.createRandom();
  const audit = await ethers.getContractAt("SentinelAudit", deployment.address);
  if ((await audit.owner()).toLowerCase() !== owner.address.toLowerCase()) throw new Error("Local owner mismatch");
  if (await ethers.provider.getBalance(writer.address) < ethers.parseEther("0.1")) {
    await (await owner.sendTransaction({to: writer.address, value: ethers.parseEther("1")})).wait();
  }
  if (!await audit.writers(writer.address)) await (await audit.authorizeWriter(writer.address, true)).wait();
  const temporary = output + ".tmp";
  fs.writeFileSync(temporary, ["# DEVELOPMENT ONLY. Never use this funded local writer on a public network.",
    "BLOCKCHAIN_ENABLED=true", "BLOCKCHAIN_RPC_URL=http://127.0.0.1:8545", "BLOCKCHAIN_CHAIN_ID=31337",
    `BLOCKCHAIN_CONTRACT_ADDRESS=${deployment.address}`, `BLOCKCHAIN_WRITER_PRIVATE_KEY=${writer.privateKey}`,
    `BLOCKCHAIN_AUDIT_HMAC_KEY=${previous.BLOCKCHAIN_AUDIT_HMAC_KEY || crypto.randomBytes(32).toString("hex")}`,
    `BLOCKCHAIN_AUDIT_HMAC_KEY_ID=${previous.BLOCKCHAIN_AUDIT_HMAC_KEY_ID || "local-v1"}`, ""
  ].join("\n"), {mode: 0o600});
  fs.renameSync(temporary, output);
  console.log("Local audit configuration ready; existing writer and HMAC secrets preserved. Secrets were not printed.");
  console.log("A restarted Hardhat node has no previous chain history; old audit proofs require their original chain.");
}
main().catch(() => {console.error("Local configuration failed; check deployment and whether configuration already exists."); process.exitCode=1;});
