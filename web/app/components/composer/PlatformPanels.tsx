"use client";

import { useEffect, useState } from "react";
import { call } from "@/lib/client";
import type { ComposerAccount, MediaRef } from "@/lib/types.composer";

type Extra = Record<string, unknown>;
type Props = { workspaceId: string; account: ComposerAccount; extra: Extra; onChange: (e: Extra) => void; pickImage: (cb: (a: MediaRef) => void) => void; media: MediaRef[] };

const field = (label: string, input: React.ReactNode) => (
  <label className="block">
    <span className="text-xs" style={{ color: "var(--muted)" }}>
      {label}
    </span>
    {input}
  </label>
);

function Check({ label, checked, onChange, disabled }: { label: string; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <label className="flex items-center gap-2 text-xs">
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

function ImagePick({ label, url, onPick, onClear }: { label: string; url?: string; onPick: () => void; onClear: () => void }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      {url ? <img src={url} alt="" className="h-10 w-16 rounded object-cover" /> : <span className="flex h-10 w-16 items-center justify-center rounded" style={{ background: "#f5f5f5", color: "var(--muted)" }}>none</span>}
      <button className="btn" onClick={onPick}>
        {label}
      </button>
      {url && (
        <button className="underline" style={{ color: "var(--muted)" }} onClick={onClear}>
          remove
        </button>
      )}
    </div>
  );
}

export function YouTubePanel({ extra, onChange, pickImage }: Props) {
  const tags = Array.isArray(extra.tags) ? (extra.tags as string[]).join(", ") : String(extra.tags ?? "");
  return (
    <div className="space-y-2">
      {field(
        "Privacy",
        <select className="input" value={String(extra.privacy_status ?? "public")} onChange={(e) => onChange({ ...extra, privacy_status: e.target.value })}>
          <option value="public">Public</option>
          <option value="unlisted">Unlisted</option>
          <option value="private">Private</option>
        </select>,
      )}
      <Check label="Made for kids" checked={!!(extra.made_for_kids ?? extra.self_declared_made_for_kids)} onChange={(v) => onChange({ ...extra, made_for_kids: v })} />
      {field("Video tags (comma separated)", <input className="input" value={tags} onChange={(e) => onChange({ ...extra, tags: e.target.value })} />)}
      <ImagePick label="Thumbnail" url={extra.thumbnail_url as string | undefined} onPick={() => pickImage((a) => onChange({ ...extra, thumbnail_asset_id: a.id, thumbnail_url: a.thumbnail_url ?? a.url }))} onClear={() => onChange({ ...extra, thumbnail_asset_id: null, thumbnail_url: undefined })} />
    </div>
  );
}

export function PinterestPanel({ workspaceId, account, extra, onChange, pickImage }: Props) {
  const [boards, setBoards] = useState<{ id: string; name: string }[] | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    call<{ boards: { id: string; name: string }[] }>(`/api/web/workspaces/${workspaceId}/composer/pinterest-boards/${account.id}`)
      .then((r) => setBoards(r.boards))
      .catch((e) => setErr(e.message));
  }, [workspaceId, account.id]);
  return (
    <div className="space-y-2">
      {field(
        "Board (required)",
        boards ? (
          <select className="input" value={String(extra.board_id ?? "")} onChange={(e) => onChange({ ...extra, board_id: e.target.value })}>
            <option value="">Choose a board</option>
            {boards.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        ) : (
          <span className="block text-xs" style={{ color: err ? "var(--bad)" : "var(--muted)" }}>
            {err || "Loading boards…"}
          </span>
        ),
      )}
      {field("Link URL", <input className="input" value={String(extra.link_url ?? "")} onChange={(e) => onChange({ ...extra, link_url: e.target.value })} />)}
      {field("Alt text", <input className="input" value={String(extra.alt_text ?? "")} onChange={(e) => onChange({ ...extra, alt_text: e.target.value })} />)}
      {field("Tag products", <input className="input" value={String(extra.tag_products ?? "")} onChange={(e) => onChange({ ...extra, tag_products: e.target.value })} />)}
      <Check label="Allow comments" checked={!!extra.allow_comments} onChange={(v) => onChange({ ...extra, allow_comments: v })} />
      <Check label="Show similar products" checked={!!extra.show_similar_products} onChange={(v) => onChange({ ...extra, show_similar_products: v })} />
      <ImagePick label="Cover image" url={extra.cover_image_url as string | undefined} onPick={() => pickImage((a) => onChange({ ...extra, cover_image_asset_id: a.id, cover_image_url: a.thumbnail_url ?? a.url }))} onClear={() => onChange({ ...extra, cover_image_asset_id: null, cover_image_url: undefined })} />
    </div>
  );
}

type Creator = { available: boolean; error?: string; creator_nickname: string; privacy_level_options: string[]; comment_disabled: boolean; duet_disabled: boolean; stitch_disabled: boolean; max_video_post_duration_sec: number | null };

const PRIVACY_LABEL: Record<string, string> = {
  PUBLIC_TO_EVERYONE: "Everyone",
  MUTUAL_FOLLOW_FRIENDS: "Friends",
  FOLLOWER_OF_CREATOR: "Followers",
  SELF_ONLY: "Only me",
};

export function TikTokPanel({ workspaceId, account, extra, onChange, media }: Props) {
  const [info, setInfo] = useState<Creator | null>(null);
  useEffect(() => {
    call<Creator>(`/api/web/workspaces/${workspaceId}/composer/tiktok-creator-info/${account.id}`)
      .then(setInfo)
      .catch(() => setInfo(null));
  }, [workspaceId, account.id]);
  // Stored form uses disable_*; the panel edits allow_* so both shapes are read here.
  const allow = (k: "comment" | "duet" | "stitch") => (extra[`allow_${k}`] !== undefined ? !!extra[`allow_${k}`] : extra[`disable_${k}`] === undefined ? false : !extra[`disable_${k}`]);
  const brandOrganic = !!(extra.brand_organic ?? extra.brand_organic_toggle);
  const brandContent = !!(extra.brand_content ?? extra.brand_content_toggle);
  const options = info?.privacy_level_options?.length ? info.privacy_level_options : Object.keys(PRIVACY_LABEL);
  const video = media.find((m) => m.media_type === "video");
  const coverSec = extra.video_cover_timestamp_ms !== undefined && extra.video_cover_timestamp_ms !== "" ? Number(extra.video_cover_timestamp_ms) / 1000 : "";
  return (
    <div className="space-y-2">
      {info?.creator_nickname && (
        <p className="text-xs" style={{ color: "var(--muted)" }}>
          Posting as {info.creator_nickname}
          {info.max_video_post_duration_sec ? ` · max ${info.max_video_post_duration_sec}s` : ""}
        </p>
      )}
      {info && !info.available && (
        <p className="text-xs" style={{ color: "var(--muted)" }}>
          Creator settings unavailable ({info.error}); defaults shown.
        </p>
      )}
      {field(
        "Who can view (required)",
        <select className="input" value={String(extra.privacy_level ?? "")} onChange={(e) => onChange({ ...extra, privacy_level: e.target.value })}>
          <option value="">Choose</option>
          {options.map((o) => (
            <option key={o} value={o}>
              {PRIVACY_LABEL[o] ?? o}
            </option>
          ))}
        </select>,
      )}
      <div className="grid grid-cols-3 gap-1">
        <Check label="Comments" checked={allow("comment")} disabled={info?.comment_disabled} onChange={(v) => onChange({ ...extra, allow_comment: v })} />
        <Check label="Duet" checked={allow("duet")} disabled={info?.duet_disabled} onChange={(v) => onChange({ ...extra, allow_duet: v })} />
        <Check label="Stitch" checked={allow("stitch")} disabled={info?.stitch_disabled} onChange={(v) => onChange({ ...extra, allow_stitch: v })} />
      </div>
      <Check label="Promotes myself or my business (brand organic)" checked={brandOrganic} onChange={(v) => onChange({ ...extra, brand_organic: v })} />
      <Check label="Paid partnership (branded content)" checked={brandContent} onChange={(v) => onChange({ ...extra, brand_content: v })} />
      {(brandOrganic || brandContent) && (
        <p className="text-xs" style={{ color: "var(--muted)" }}>
          {brandContent ? "Labelled “Paid partnership”." : "Labelled “Promotional content”."} By posting you agree to TikTok&apos;s Branded Content Policy.
        </p>
      )}
      <Check label="AI-generated content" checked={!!extra.is_aigc} onChange={(v) => onChange({ ...extra, is_aigc: v })} />
      {video &&
        field(
          "Cover frame (seconds into the video; blank = first frame)",
          <input className="input w-40" type="number" min={0} step={0.1} value={coverSec} onChange={(e) => onChange({ ...extra, video_cover_timestamp_ms: e.target.value === "" ? "" : Math.round(Number(e.target.value) * 1000) })} />,
        )}
    </div>
  );
}

export function PlatformPanel(props: Props) {
  switch (props.account.platform) {
    case "youtube":
      return <YouTubePanel {...props} />;
    case "pinterest":
      return <PinterestPanel {...props} />;
    case "tiktok":
      return <TikTokPanel {...props} />;
    default:
      return null;
  }
}
