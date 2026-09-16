// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @notice Opaque audit commitments only. This contract does not verify identities.
contract SentinelAudit {
    enum RecordType { SCREENING_RESULT, OFFICER_DECISION }
    struct AuditRecord { bytes32 digest; uint256 timestamp; address submitter; bool exists; }
    address public immutable owner;
    mapping(address => bool) public writers;
    mapping(bytes32 => mapping(RecordType => mapping(uint256 => AuditRecord))) private records;
    event WriterAuthorized(address indexed writer, bool authorized);
    event AuditAnchored(bytes32 indexed caseKey, RecordType indexed recordType, uint256 indexed version,
                        bytes32 digest, uint256 timestamp, address submitter);

    constructor() { owner = msg.sender; writers[msg.sender] = true; }

    function authorizeWriter(address writer, bool authorized) external {
        require(msg.sender == owner, "Only owner");
        require(writer != address(0), "Zero writer");
        writers[writer] = authorized;
        emit WriterAuthorized(writer, authorized);
    }

    function anchorRecord(bytes32 caseKey, RecordType recordType, uint256 version, bytes32 digest) external {
        require(writers[msg.sender], "Unauthorized writer");
        require(caseKey != bytes32(0) && digest != bytes32(0) && version > 0, "Invalid record");
        require(!records[caseKey][recordType][version].exists, "Already anchored");
        records[caseKey][recordType][version] = AuditRecord(digest, block.timestamp, msg.sender, true);
        emit AuditAnchored(caseKey, recordType, version, digest, block.timestamp, msg.sender);
    }

    function getRecord(bytes32 caseKey, RecordType recordType, uint256 version) external view returns (AuditRecord memory) {
        return records[caseKey][recordType][version];
    }

    function recordExists(bytes32 caseKey, RecordType recordType, uint256 version) external view returns (bool) {
        return records[caseKey][recordType][version].exists;
    }
}
