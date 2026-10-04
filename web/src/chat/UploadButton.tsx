export function UploadButton({ onUploaded }: { onUploaded: (uploadId: string) => void }) {
  // TODO: POST /api/conversations/{id}/upload, then pass upload_id to ask.
  void onUploaded
  return (
    <label>
      <span>Upload</span>
      <input type="file" hidden />
    </label>
  )
}
