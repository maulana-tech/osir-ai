export interface MediaAsset {
  id: string;
  filename: string;
  media_type: "image" | "video" | "gif" | "document" | string;
  mime_type: string;
  file_size: number;
  file_size_display: string;
  width: number;
  height: number;
  duration: number;
  title: string;
  alt_text: string;
  tags: string[];
  folder_id: string | null;
  is_starred: boolean;
  is_shared: boolean;
  processing_status: "pending" | "processing" | "completed" | "failed" | string;
  url: string;
  thumbnail_url: string | null;
  uploaded_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface MediaVersion {
  id: string;
  number: number;
  description: string;
  thumbnail_url: string | null;
  is_current: boolean;
  created_by: string | null;
  created_at: string;
}

export interface MediaFolder {
  id: string;
  name: string;
  children: MediaFolder[];
}

export interface Library {
  assets: MediaAsset[];
  page: number;
  num_pages: number;
  total: number;
  folders?: MediaFolder[];
  file_types: { value: string; label: string }[];
  accepted_file_types: string;
  max_bulk_upload: number;
  can?: { upload_media: boolean; edit_media: boolean; delete_media: boolean; manage_media: boolean };
  is_admin?: boolean;
}

export interface AssetDetail {
  asset: MediaAsset;
  versions: MediaVersion[];
  download_url: string;
}

/** Which library a component is working on and what the viewer may do there. */
export interface LibraryScope {
  apiBase: string;
  pageBase: string;
  shared: boolean;
  canUpload: boolean;
  canEdit: boolean;
  canDelete: boolean;
  canManageFolders: boolean;
}
