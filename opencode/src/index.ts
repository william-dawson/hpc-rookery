/**
 * OpenCode plugin for hpc-rookery: harness glue, not a second engine.
 *
 * Registers the two MCP servers every facility shares — the same
 * `uv tool run --from git+...` command plugins/hpc/.mcp.json gives Codex and
 * Claude Code and pi/extension.ts gives Pi — and contributes the Agent
 * Skills-format facility skill packs for the facilities selected with /hpc.
 * The Python servers stay the single engine; this file never reimplements a
 * tool.
 *
 * Facility selection, in precedence order:
 *   1. plugin storage, set by /hpc (persists across sessions)
 *   2. the `facilities` plugin option (the initial selection)
 *   3. none — only the shared hpc-facilities skill loads
 *
 * Other options (object form in opencode.json, read via ctx.options):
 *   gitRef: string  the `uv --from` requirement for both servers
 *                   (default: git+...@main; override to test a branch)
 *
 * No client-side argument rule is needed here, unlike Pi: OpenCode does not
 * pre-validate MCP tool arguments against the server's schema, and the
 * server's pydantic accepts a spec as either an object or a JSON string.
 */
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { Plugin, Skill, type Mcp } from "@opencode/plugin";

/**
 * BRANCH-ONLY scaffolding — do not merge to main. Installs from this
 * branch must also RUN servers from this branch, or a plugin-add test
 * of the schema fix would silently exercise @main schemas.
 */
const PKG_REF_DEFAULT = "git+https://github.com/william-dawson/hpc-rookery.git@fix/inline-tool-schema-refs";

/**
 * The plugin lives at <repo>/opencode/src/index.ts, whether that repo is a
 * checkout (local path config) or an installed git package (the whole
 * repository is the npm package — see the root package.json).
 */
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");

interface Facility {
	slug: string;
	display_name: string;
}

/** Read facilities/<slug>/facility.json — packaged data in every copy. */
function discoverFacilities(): Map<string, Facility> {
	const dir = join(repoRoot, "facilities");
	const known = new Map<string, Facility>();
	if (!existsSync(dir)) return known;
	for (const name of readdirSync(dir)) {
		const file = join(dir, name, "facility.json");
		if (!existsSync(file)) continue;
		try {
			const facility = JSON.parse(readFileSync(file, "utf8")) as Facility;
			if (typeof facility.slug === "string" && typeof facility.display_name === "string") {
				known.set(facility.slug, facility);
			}
		} catch {
			// A malformed facility.json must not take the plugin down —
			// the same never-fail-to-start spirit the MCP server follows.
		}
	}
	return known;
}

/** Parse the SKILL.md frontmatter this repo's generated skills all carry. */
function parseFrontmatter(text: string): { name?: string; description?: string; body: string } {
	if (!text.startsWith("---\n")) return { body: text };
	const end = text.indexOf("\n---\n", 4);
	if (end === -1) return { body: text };
	const front = text.slice(4, end);
	const body = text.slice(end + 5);
	const name = /^name:\s*(.+)$/m.exec(front)?.[1]?.trim();
	const description = /^description:\s*(.+)$/m.exec(front)?.[1]?.trim();
	return { name, description, body };
}

/** Collect Skill.Info entries for the base pack plus each selected facility. */
function skillEntries(packs: string[]): Skill.Info[] {
	const entries: Skill.Info[] = [];
	for (const pack of packs) {
		const dir = join(repoRoot, "plugins", pack, "skills");
		if (!existsSync(dir)) continue;
		for (const name of readdirSync(dir)) {
			const path = join(dir, name, "SKILL.md");
			if (!existsSync(path)) continue;
			const parsed = parseFrontmatter(readFileSync(path, "utf8"));
			if (!parsed.name) continue; // malformed skill: let the loader skip it
			entries.push({
				id: Skill.ID.make(name),
				name: Skill.Name.make(parsed.name),
				description: parsed.description,
				path: Skill.Info.fields.path.make(path),
				content: parsed.body,
			});
		}
	}
	return entries;
}

export default Plugin.define({
	id: "hpc-rookery",
	async setup(ctx) {
		const options = ctx.options as { facilities?: unknown; gitRef?: unknown };
		const gitRef =
			typeof options.gitRef === "string" && options.gitRef.trim()
				? options.gitRef.trim()
				: PKG_REF_DEFAULT;

		const known = discoverFacilities();
		const available = [...known.keys()].sort();

		// Fail loud on a config typo, and on a copy that lost the repo
		// layout it reads skills and facilities from.
		const optionFacilities = Array.isArray(options.facilities)
			? options.facilities.filter((slug): slug is string => typeof slug === "string")
			: [];
		if (known.size === 0 && optionFacilities.length > 0) {
			throw new Error(
				"hpc-rookery plugin: facilities/ not found next to the plugin — " +
					"it must load from a full checkout or a repository install, not a bare copy",
			);
		}
		const unknownOption = optionFacilities.filter((slug) => !known.has(slug));
		if (unknownOption.length > 0) {
			throw new Error(
				`hpc-rookery plugin: unknown facility slug(s): ${unknownOption.join(", ")} — ` +
					`valid: ${available.join(", ")}`,
			);
		}

		// The /hpc choice, persisted in plugin storage, overrides the
		// initial option. Transforms re-read this on every reload.
		let selected: string[] | undefined = undefined;
		const stored = await ctx.storage.get("facilities");
		if (Array.isArray(stored)) {
			selected = stored.filter((slug): slug is string => typeof slug === "string" && known.has(slug));
		}
		const selectedFacilities = (): string[] => selected ?? optionFacilities;

		const server = (entry: string): Mcp.ServerConfig => ({
			type: "local",
			command: ["uv", "tool", "run", "--quiet", "--from", gitRef, entry],
			// The skill packs instruct the model to call tools by name, so
			// keep them on the provider's native tool list (hpc_submit_job)
			// instead of behind Code Mode's tools.hpc.submit_job namespace.
			codemode: false,
			// uv cold-resolves the git ref on the very first launch; the
			// 30s startup default is too tight for that.
			timeout: { startup: 120_000 },
		});

		const registrations = [
			await ctx.mcp.transform((editor) => {
				editor.set("hpc", server("hpc-mcp"));
				editor.set("hpc-docs", server("hpc-docs-mcp"));
			}),
			await ctx.skill.transform((editor) => {
				for (const skill of skillEntries(["hpc", ...selectedFacilities().map((slug) => `hpc-${slug}`)])) {
					editor.add(skill);
				}
			}),
			await ctx.command.transform((editor) => {
				editor.add({
					name: "hpc",
					description: "Set the HPC facility skill packs: /hpc <slug>[,<slug>...], /hpc clear, /hpc to list",
					execute: async ({ sessionID, prompt, delivery }) => {
						const reply = (text: string) =>
							ctx.session.prompt({ ...prompt, sessionID, text, delivery });
						const args = prompt.text.trim();

						if (known.size === 0) {
							await reply(
								"The hpc-rookery plugin cannot find facilities/ next to itself — " +
									"it needs a full repository install. Tell the user to reinstall it.",
							);
							return;
						}
						if (args === "") {
							const current = selectedFacilities();
							await reply(
								`HPC facility skill packs currently loaded: ${current.length > 0 ? current.join(", ") : "(none)"}.\n` +
									`Available facilities: ${available.join(", ")}.\n` +
									"Report this to the user; no other action is needed.",
							);
							return;
						}

						let slugs: string[];
						if (args === "clear") {
							slugs = [];
						} else {
							slugs = [...new Set(args.split(/[,\s]+/).filter(Boolean))];
							const unknown = slugs.filter((slug) => !known.has(slug));
							if (unknown.length > 0) {
								await reply(
									`Unknown facility slug(s): ${unknown.join(", ")} — valid: ${available.join(", ")}. ` +
										"Report this to the user; nothing was changed.",
								);
								return;
							}
						}

						selected = slugs;
						await ctx.storage.set("facilities", slugs);
						await ctx.skill.reload();
						await reply(
							slugs.length > 0
								? `HPC facility skill packs are now set to: ${slugs.join(", ")} — the packs are loaded. Confirm this to the user.`
								: "HPC facility skill packs cleared — only the shared hpc-facilities skill remains. Confirm this to the user.",
						);
					},
				});
			}),
		];

		return async () => {
			for (const registration of registrations) await registration.dispose();
		};
	},
});
