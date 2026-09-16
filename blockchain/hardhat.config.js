require("dotenv").config();
require("@nomicfoundation/hardhat-ethers");
const { subtask } = require("hardhat/config");
const { TASK_COMPILE_SOLIDITY_GET_SOLC_BUILD } = require("hardhat/builtin-tasks/task-names");
// Pinned npm compiler: compiling does not need a second compiler download.
subtask(TASK_COMPILE_SOLIDITY_GET_SOLC_BUILD).setAction(async ({ solcVersion }, _hre, runSuper) => {
  if (solcVersion === "0.8.28") return { compilerPath: require.resolve("solc/soljson.js"), isSolcJs: true, version: solcVersion, longVersion: require("solc").version() };
  return runSuper();
});
module.exports = {
  solidity: {version: "0.8.28", settings: {optimizer: {enabled: true, runs: 200}}},
  networks: {
    hardhat: {chainId: 31337},
    localhost: {url: process.env.BLOCKCHAIN_RPC_URL || "http://127.0.0.1:8545", chainId: 31337},
    testnet: {url: process.env.TESTNET_RPC_URL || "http://127.0.0.1:8545", accounts: process.env.DEPLOYER_PRIVATE_KEY ? [process.env.DEPLOYER_PRIVATE_KEY] : []}
  }
};
