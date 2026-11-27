/** Sends a file to a presigned POST slot (Phase 6 M3, ADR-064).
 *
 * A multipart POST is a CORS "simple" request: sent without CORS on the object store, the
 * response is opaque. The server checks the stored object (size, type) after the confirmation,
 * so a failed upload shows up as a rejected file. */
export async function postToSlot(
  slot: { url: string; fields: Record<string, string> },
  file: File,
): Promise<void> {
  const form = new FormData();
  for (const [key, value] of Object.entries(slot.fields)) form.append(key, value);
  form.append("file", file); // the file goes last in an S3 POST form
  await fetch(slot.url, { method: "POST", body: form, mode: "no-cors", credentials: "omit" });
}
