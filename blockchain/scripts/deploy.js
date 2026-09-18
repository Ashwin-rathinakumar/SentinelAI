const { ethers, artifacts } = require("hardhat");
const fs = require("node:fs");
const path = require("node:path");
async function main() {
  const chainId = Number((await ethers.provider.getNetwork()).chainId);
  if (![31337, 80002, 11155111].includes(chainId)) throw new Error("Deployment restricted to local / test networks");
  const deploymentPath = path.join(__dirname, "../deployments/local.json");
  if (chainId === 31337 && fs.existsSync(deploymentPath)) {
    const saved = JSON.parse(fs.readFileSync(deploymentPath, "utf8"));
    if (saved.chainId === chainId && await ethers.provider.getCode(saved.address) !== "0x") {
      const existing = await ethers.getContractAt("SentinelAudit", saved.address);
      const [owner] = await ethers.getSigners();
      if ((await existing.owner()).toLowerCase() !== owner.address.toLowerCase()) throw new Error("Existing contract owner mismatch");
      await existing.recordExists(ethers.ZeroHash, 0, 1);
      console.log(`Reusing live local audit contract: ${saved.address}\nChain ID: ${chainId}`);
      return;
    }
  }
  const contract = await ethers.deployContract("SentinelAudit");
  await contract.waitForDeployment();
  const address = await contract.getAddress();
  const receipt = await contract.deploymentTransaction().wait();
  fs.mkdirSync(path.join(__dirname, "../deployments"), {recursive: true});
  fs.writeFileSync(deploymentPath, JSON.stringify({address, chainId, transactionHash: receipt.hash, blockNumber: receipt.blockNumber}, null, 2));
  const artifact = await artifacts.readArtifact("SentinelAudit");
  fs.writeFileSync(path.join(__dirname, "../../backend/app/services/sentinel_audit_abi.json"), JSON.stringify(artifact.abi, null, 2) + "\n");
  console.log(`SentinelAudit deployed at: ${address}\nChain ID: ${chainId}\nTransaction: ${receipt.hash}\nBlock: ${receipt.blockNumber}`);
}
main().catch(() => { console.error("Deployment failed. Check network, signer and contract configuration."); process.exitCode = 1; });
