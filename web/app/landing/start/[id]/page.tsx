import { redirect } from "next/navigation";

/** Old per-channel sign-up pages: pricing needs no account any more, so they all lead to /start. */
export default function ChannelStartPage() {
  redirect("/start");
}
