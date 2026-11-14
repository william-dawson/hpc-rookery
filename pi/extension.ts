/**
 * Pi extension for hpc-rookery: harness glue, not a second engine.
 *
 * What it does:
 *   - registers the two MCP servers every facility shares (`hpc`,
 *     `hpc-docs`) with the same stdio command plugins/hpc/.mcp.json gives
 *     Codex and Claude Code — the Python server stays the single engine;
 *   - contributes the shared `hpc-facilities` skill plus the Agent
 *     Skills-format facility skill packs the user selected with `/hpc`;
 *   - gates `fs_rm`, the one destructive tool, behind a confirmation.
 *
 * Repo rules honored here: nothing writes to stdout (Pi's RPC and MCP
 * stdio transports own it — user feedback goes through ctx.ui), and
 * per-facility access configuration is still read lazily by the server at
 * tool-call time; this extension reads only packaged data
 * (facilities/<slug>/facility.json and the plugins/ skill directories).
 */

import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
	CONFIG_DIR_NAME,
	type ExtensionAPI,
	type ExtensionCommandContext,
	type ExtensionContext,
} from "@earendil-works/pi-coding-agent";
import { type AutocompleteItem, Key, matchesKey, truncateToWidth } from "@earendil-works/pi-tui";

/** Same install ref as plugins/hpc/.mcp.json — one source of truth per user. */
const PKG_REF = "git+https://github.com/william-dawson/hpc-rookery.git@main";

/** The extension always lives at <repo>/pi/extension.ts, whatever loaded it. */
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..");

/** The shared facility-discovery skill, contributed in every session. */
const baseSkillsDir = join(repoRoot, "plugins", "hpc", "skills");

/**
 * Selected facility slugs. HPC access is a property of the user (their ssh
 * config, their ~/.hpc-agent), not of a project, so the selection is global.
 */
const configFile = join(homedir(), CONFIG_DIR_NAME, "agent", "hpc-rookery.json");

interface Facility {
	slug: string;
	display_name: string;
	description: string;
	scheduler: string;
	live_validated?: boolean;
}

/** Read each facilities/<slug>/facility.json — packaged data, present in every install. */
function discoverFacilities(): Facility[] {
	const dir = join(repoRoot, "facilities");
	if (!existsSync(dir)) return [];
	const facilities: Facility[] = [];
	for (const name of readdirSync(dir)) {
		const file = join(dir, name, "facility.json");
		if (!existsSync(file)) continue;
		try {
			const facility = JSON.parse(readFileSync(file, "utf8")) as Facility;
			if (typeof facility.slug === "string" && typeof facility.display_name === "string") {
				facilities.push(facility);
			}
		} catch {
			// A malformed facility.json must not take the extension down —
			// the same never-fail-to-start spirit the MCP server follows.
		}
	}
	return facilities.sort((a, b) => a.slug.localeCompare(b.slug));
}

/** The saved selection, filtered to facilities this checkout still knows. */
function loadSelection(known: Facility[]): Set<string> {
	const slugs = new Set(known.map((f) => f.slug));
	try {
		const saved = JSON.parse(readFileSync(configFile, "utf8")) as { facilities?: unknown };
		if (!Array.isArray(saved.facilities)) return new Set();
		return new Set(
			saved.facilities.filter((s): s is string => typeof s === "string" && slugs.has(s)),
		);
	} catch {
		return new Set(); // missing or unreadable — same as nothing selected yet
	}
}

function saveSelection(slugs: string[]): void {
	mkdirSync(dirname(configFile), { recursive: true });
	writeFileSync(configFile, `${JSON.stringify({ facilities: slugs }, null, "\t")}\n`);
}

/** The stdio command that launches a server — identical to .mcp.json's. */
const uvToolRun = (entry: string): string[] => ["tool", "run", "--quiet", "--from", PKG_REF, entry];

/**
 * Interactive multi-select for facility packs. Returns the chosen slugs, or
 * null when cancelled. TUI-only: non-interactive sessions use /hpc set.
 */
function pickFacilities(
	ctx: ExtensionContext,
	facilities: Facility[],
	initial: Set<string>,
): Promise<string[] | null> {
	return ctx.ui.custom<string[] | null>((tui, theme, keybindings, done) => {
		const selected = new Set(initial);
		let cursor = 0;
		let cache: string[] | undefined;

		const refresh = () => {
			cache = undefined;
			tui.requestRender();
		};

		return {
			render(width: number): string[] {
				if (cache) return cache;
				const lines: string[] = [
					theme.fg("accent", theme.bold("HPC facility skill packs")),
					theme.fg("dim", "Space toggles · Enter applies (then reloads) · Esc cancels"),
					"",
				];
				facilities.forEach((facility, i) => {
					const atCursor = i === cursor;
					const checked = selected.has(facility.slug);
					const marker = atCursor ? theme.fg("accent", "❯ ") : "  ";
					const label =
						`${checked ? "[x]" : "[ ]"} ${facility.slug} — ${facility.display_name}` +
						` (${facility.scheduler}${facility.live_validated ? "" : ", not yet live-validated"})`;
					lines.push(
						truncateToWidth(marker + theme.fg(checked ? "text" : "muted", label), width),
					);
					if (atCursor && facility.description) {
						lines.push(truncateToWidth(theme.fg("dim", `    ${facility.description}`), width));
					}
				});
				lines.push("", theme.fg("dim", `${selected.size} of ${facilities.length} selected`));
				cache = lines;
				return lines;
			},
			handleInput(data: string): void {
				if (keybindings.matches(data, "tui.select.up")) {
					cursor = Math.max(0, cursor - 1);
					refresh();
				} else if (keybindings.matches(data, "tui.select.down")) {
					cursor = Math.min(facilities.length - 1, cursor + 1);
					refresh();
				} else if (matchesKey(data, Key.space)) {
					const slug = facilities[cursor]?.slug;
					if (slug) {
						if (selected.has(slug)) selected.delete(slug);
						else selected.add(slug);
						refresh();
					}
				} else if (keybindings.matches(data, "tui.select.confirm")) {
					done([...selected]);
				} else if (keybindings.matches(data, "tui.select.cancel")) {
					done(null);
				}
			},
			invalidate(): void {
				cache = undefined;
			},
		};
	});
}

export default function (pi: ExtensionAPI) {
	const facilities = discoverFacilities();

	// -----------------------------------------------------------------------
	// The two MCP servers — the Python servers remain the single engine.
	// -----------------------------------------------------------------------

	pi.registerMcpServer("hpc", {
		command: "uv",
		args: uvToolRun("hpc-mcp"),
		// Direct: these tools are the point of the session, and the skill
		// packs instruct the model to call them by name.
		exposure: "direct",
		description:
			"HPC cluster operations for every hpc-rookery facility: run commands on login nodes, submit and monitor jobs, manage files. Every tool takes an explicit `facility` slug as its first argument — get valid slugs from get_facilities.",
		// Job and file operations travel over SSH; 60s is tight for them.
		timeout: 300,
	});

	pi.registerMcpServer("hpc-docs", {
		command: "uv",
		args: uvToolRun("hpc-docs-mcp"),
		// Deferred: the three docs tools surface via tool_search when a
		// facility guide is needed, instead of always declaring schemas.
		exposure: "deferred",
		description:
			"Search and read the bundled per-facility machine guides (search_docs, list_doc_sections, read_doc_section) via tool_search.",
		timeout: 120,
	});

	// -----------------------------------------------------------------------
	// Skills: the base pack always, facility packs per saved selection.
	// -----------------------------------------------------------------------

	pi.on("resources_discover", () => {
		const skillPaths: string[] = [];
		if (existsSync(baseSkillsDir)) skillPaths.push(baseSkillsDir);
		for (const slug of loadSelection(facilities)) {
			const dir = join(repoRoot, "plugins", `hpc-${slug}`, "skills");
			if (existsSync(dir)) skillPaths.push(dir);
		}
		return { skillPaths };
	});

	pi.on("session_start", (_event, ctx) => {
		if (facilities.length === 0 || !ctx.hasUI) return;
		if (loadSelection(facilities).size > 0) return;
		ctx.ui.notify(
			"No HPC facility skill packs selected — run /hpc to choose which machines load skills.",
			"info",
		);
	});

	// -----------------------------------------------------------------------
	// /hpc — which facility skill packs load.
	// -----------------------------------------------------------------------

	/** Save the selection and reload, since resources_discover runs at startup. */
	async function applySelection(ctx: ExtensionCommandContext, slugs: string[]): Promise<void> {
		saveSelection(slugs);
		ctx.ui.notify(
			slugs.length > 0
				? `Facility skill packs set to: ${slugs.join(", ")} — reloading…`
				: "Facility skill packs cleared — reloading…",
			"info",
		);
		// Terminal for this handler: nothing may run after ctx.reload().
		await ctx.reload();
	}

	pi.registerCommand("hpc", {
		description: "Choose which HPC facility skill packs load (list, set, clear)",
		getArgumentCompletions: (prefix: string): AutocompleteItem[] | null => {
			const items: AutocompleteItem[] = [
				{ value: "list", label: "list", description: "Show selected and available facility packs" },
				{ value: "set", label: "set", description: "Set the selected packs, e.g. set rikyu,fugaku" },
				{ value: "clear", label: "clear", description: "Load no facility packs" },
				...facilities.map((facility) => ({
					value: facility.slug,
					label: facility.slug,
					description: facility.description,
				})),
			];
			const filtered = items.filter((item) => item.value.startsWith(prefix));
			return filtered.length > 0 ? filtered : null;
		},
		handler: async (args, ctx) => {
			const [sub, ...rest] = args.trim().split(/\s+/).filter(Boolean);

			if (facilities.length === 0) {
				ctx.ui.notify(
					"facilities/*/facility.json not found next to the Pi extension — " +
						"install the full repository (pi install git:github.com/william-dawson/hpc-rookery@main).",
					"error",
				);
				return;
			}

			if (!sub) {
				if (ctx.mode !== "tui") {
					ctx.ui.notify(
						"The interactive picker needs the TUI — use /hpc set <slug>,<slug> instead.",
						"warning",
					);
					return;
				}
				const chosen = await pickFacilities(ctx, facilities, loadSelection(facilities));
				if (chosen === null) {
					ctx.ui.notify("Facility selection unchanged.", "info");
					return;
				}
				await applySelection(ctx, chosen);
				return;
			}

			if (sub === "list") {
				const selected = loadSelection(facilities);
				ctx.ui.notify(
					`Selected packs: ${selected.size > 0 ? [...selected].join(", ") : "(none)"}\n` +
						`Available: ${facilities.map((facility) => facility.slug).join(", ")}`,
					"info",
				);
				return;
			}

			if (sub === "set") {
				const slugs = [...new Set(rest.join(",").split(/[,\s]+/).filter(Boolean))];
				if (slugs.length === 0) {
					ctx.ui.notify("No slugs given — /hpc set rikyu,fugaku (or /hpc clear).", "error");
					return;
				}
				const known = new Set(facilities.map((facility) => facility.slug));
				const unknown = slugs.filter((slug) => !known.has(slug));
				if (unknown.length > 0) {
					ctx.ui.notify(
						`Unknown facility slug(s): ${unknown.join(", ")} — ` +
							`valid: ${[...known].join(", ")}`,
						"error",
					);
					return;
				}
				await applySelection(ctx, slugs);
				return;
			}

			if (sub === "clear") {
				await applySelection(ctx, []);
				return;
			}

			ctx.ui.notify(
				`Unknown /hpc subcommand "${sub}" — use /hpc (picker), list, set <slugs>, or clear.`,
				"error",
			);
		},
	});

	// -----------------------------------------------------------------------
	// Safety gate: fs_rm is the one destructive tool on shared filesystems
	// with no trash. The server's docstring already demands confirmation
	// before every call; this enforces it with real UI.
	// -----------------------------------------------------------------------

	pi.on("tool_call", async (event, ctx) => {
		if (event.toolName !== "mcp__hpc__fs_rm") return;
		const input = event.input as { facility?: string; path?: string; recursive?: boolean };
		const target =
			`${input.facility ?? "?"}:${input.path ?? "?"}` + (input.recursive ? " (recursive)" : "");
		if (!ctx.hasUI) {
			// Fail closed: with no way to ask, there is no way to delete.
			return {
				block: true,
				reason:
					`fs_rm (${target}) requires interactive confirmation — ` +
					"rerun from an interactive or RPC session.",
			};
		}
		const ok = await ctx.ui.confirm(
			"Delete on the cluster?",
			`${target} — cluster filesystems have no trash; this cannot be undone.`,
		);
		if (!ok) {
			return { block: true, reason: `User declined deleting ${target}.` };
		}
	});
}
