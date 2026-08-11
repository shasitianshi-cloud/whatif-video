export function membershipState(status) {
  if (!status || typeof status !== "object" || typeof status.isMember !== "boolean") {
    return "unknown";
  }
  return status.isMember ? "member" : "non-member";
}

export function watermarkedDownloadForMembership(status) {
  return membershipState(status) !== "member";
}

export function buildDownloadMetadataPath(taskId, slotIndex, status) {
  if (!taskId) throw new Error("taskId required");
  if (!Number.isSafeInteger(slotIndex) || slotIndex < 0) {
    throw new Error("slotIndex must be a non-negative integer");
  }
  const query = new URLSearchParams({
    slotIndex: String(slotIndex),
    watermarked: String(watermarkedDownloadForMembership(status)),
    aiWater: "true"
  });
  return `/v2/tasks/${encodeURIComponent(taskId)}/download?${query.toString()}`;
}
