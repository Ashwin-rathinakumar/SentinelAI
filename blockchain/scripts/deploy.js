const { ethers, artifacts } = require("hardhat");
const fs = require("node:fs");
const path = require("node:path");
async function main() {
  const chainId = Number((await ethers.provider.getNetwork()).chainId);
  if (![31337, 80002, 11155111].includes(chainId)) throw new Error("Deployment restricted to local / test networks");
  const contract = await ethers.deployContract("SentinelAudit");
  await contract.waitForDeployment();
  const address = await contract.getAddress();
  const receipt = await contract.deploymentTransaction().wait();
  fs.mkdirSync(path.join(__dirname, "../deployments"), {recursive: true});
  fs.writeFileSync(path.join(__dirname, "../deployments/local.json"), JSON.stringify({address, chainId, transactionHash: receipt.hash, blockNumber: receipt.blockNumber}, null, 2));
  const artifact = await artifacts.readArtifact("SentinelAudit");
  fs.writeFileSync(path.join(__dirname, "../../backend/app/services/sentinel_audit_abi.json"), JSON.stringify(artifact.abi, null, 2) + "\n");
  console.log(`SentinelAudit deployed at: ${address}\nChain ID: ${chainId}\nTransaction: ${receipt.hash}\nBlock: ${receipt.blockNumber}`);
}
main().catch(() => { console.error("Deployment failed. Check network, signer and contract configuration."); process.exitCode = 1; });
