import {
  Tag,
  type TagToken,
  type TopLevelToken,
  type Context,
  type Emitter,
  type Template,
} from 'liquidjs';

/**
 * Power Pages {% substitution %} ... {% endsubstitution %} tag.
 *
 * In the real Power Pages engine, content inside {% substitution %} blocks
 * is rendered at request time (bypassing the output cache). Since we have
 * no caching locally, this simply renders its body content normally.
 */
export class SubstitutionTag extends Tag {
  private templates: Template[] = [];

  constructor(tagToken: TagToken, remainTokens: TopLevelToken[], liquid: any) {
    super(tagToken, remainTokens, liquid);
    this.templates = [];

    const stream = this.liquid.parser
      .parseStream(remainTokens)
      .on('tag:endsubstitution', function (this: { stop: () => void }) {
        this.stop();
      })
      .on('template', (tpl: Template) => {
        this.templates.push(tpl);
      })
      .on('end', () => {
        throw new Error(`Tag ${tagToken.getText()} not closed`);
      });

    stream.start();
  }

  *render(ctx: Context, emitter: Emitter): Generator<unknown, void, unknown> {
    const r = this.liquid.renderer;
    yield r.renderTemplates(this.templates, ctx, emitter);
  }
}
