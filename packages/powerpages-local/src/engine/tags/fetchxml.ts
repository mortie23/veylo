import type { TagToken, Context, Emitter, TopLevelToken } from 'liquidjs';

export const FetchXmlTag = {
  parse(this: any, tagToken: TagToken, remainTokens: TopLevelToken[]) {
    this.variable = tagToken.args.trim();
    this.templates = [];
    
    let token;
    while ((token = remainTokens.shift())) {
      if ((token as any).name === 'endfetchxml') {
        break;
      }
      this.templates.push(token);
    }
  },
  
  async render(this: any, ctx: Context, emitter: Emitter) {
    const fetchXmlBody = await this.liquid.renderer.renderTemplates(this.templates, ctx);
    const mockResult = {
      results: {
        entities: []
      }
    };
    ctx.bottom()[this.variable] = mockResult;
  }
};
