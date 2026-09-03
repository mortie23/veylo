import { Tag, type TagToken, type TopLevelToken, type Context, type Emitter } from 'liquidjs';

/**
 * Power Pages {% editable %} tag.
 *
 * Handles two forms:
 *   {% editable snippets 'Snippet Name' type: 'html' %}
 *   {% editable page 'adx_copy' type: 'html', liquid: true %}
 *   {% editable page 'adx_title' type: 'html', liquid: true %}
 *
 * In the local preview, this simply renders the content without the
 * CMS edit wrapper that the real Power Pages engine injects.
 */
export class EditableTag extends Tag {
  private args: string;

  constructor(tagToken: TagToken, remainTokens: TopLevelToken[], liquid: any) {
    super(tagToken, remainTokens, liquid);
    this.args = tagToken.args.trim();
  }

  *render(ctx: Context, emitter: Emitter): Generator<unknown, void, unknown> {
    if (this.args.startsWith('snippets')) {
      const match = this.args.match(/'([^']+)'/);
      if (match) {
        const snippetName = match[1];
        const snippets = ctx.get(['snippets']) as Record<string, string> | undefined;
        emitter.write(snippets?.[snippetName] ?? '');
      }
      return;
    }

    if (this.args.startsWith('page')) {
      const match = this.args.match(/'([^']+)'/);
      if (match) {
        const fieldName = match[1];
        const page = ctx.get(['page']) as Record<string, unknown> | undefined;
        const content = String(page?.[fieldName] ?? '');

        if (this.args.includes('liquid: true') && content) {
          // Re-render through Liquid to evaluate nested tags/variables
          const rendered = (yield this.liquid.parseAndRender(
            content,
            ctx.getAll(),
          )) as string;
          emitter.write(rendered);
        } else {
          emitter.write(content);
        }
      }
      return;
    }

    // Fallback: render nothing for unrecognised editable targets
    return;
  }
}
