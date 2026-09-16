// Local development only: create a funded writer and secret without printing either.
const {ethers} = require("hardhat");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
async function main() {
  if (Number((await ethers.provider.getNetwork()).chainId) !== 31337) throw new Error("Local chain required");
  const output = path.join(__dirname, "../../backend/.env.audit-local");
  if (fs.existsSync(output)) throw new Error("Local configuration already exists; refusing to replace secrets");
  const deployment = JSON.parse(fs.readFileSync(path.join(__dirname, "../deployments/local.json"), "utf8"));
  const [owner] = await ethers.getSigners();
  const writer = ethers.Wallet.createRandom();
  const audit = await ethers.getContractAt("SentinelAudit", deployment.address);
  await (await owner.sendTransaction({to: writer.address, value: ethers.parseEther("1")})).wait();
  await (await audit.authorizeWriter(writer.address, true)).wait();
  fs.writeFileSync(output, ["# DEVELOPMENT ONLY. Never use this funded local writer on a public network.",
    "BLOCKCHAIN_ENABLED=true", "BLOCKCHAIN_RPC_URL=http://127.0.0.1:8545", "BLOCKCHAIN_CHAIN_ID=31337",
    `BLOCKCHAIN_CONTRACT_ADDRESS=${deployment.address}`, `BLOCKCHAIN_WRITER_PRIVATE_KEY=${writer.privateKey}`,
    `BLOCKCHAIN_AUDIT_HMAC_KEY=${crypto.randomBytes(32).toString("hex")}`, "BLOCKCHAIN_AUDIT_HMAC_KEY_ID=local-v1", ""
  ].join("\n"), {mode: 0o600, flag: "wx"});
  console.log("Created ignored backend/.env.audit-local with a funded, authorized development writer. Secrets were not printed.");
}
main().catch(() => {console.error("Local configuration failed; check deployment and whether configuration already exists."); process.exitCode=1;});
