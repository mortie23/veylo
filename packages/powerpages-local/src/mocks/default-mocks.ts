/**
 * Built-in mock HTML templates for core Power Pages ASPX platform routes.
 * These are used as defaults if the user does not provide their own override
 * in their mockTemplatesPath folder.
 */
export const DEFAULT_MOCKS: Record<string, string> = {
  // Built-in mock for ~/Pages/Profile.aspx
  '~/Pages/Profile.aspx': `
<div class="wrapper-body" role="main">
  <div class="container" style="padding-top: 2rem; padding-bottom: 2rem;">
    <h1>{{ page.title | escape }}</h1>
    
    <div class="row">
      <div class="col-md-8">
        {{ page.copy }}
      </div>
    </div>

    <div class="row" style="margin-top: 2rem;">
      <div class="col-md-8">
        <form onsubmit="alert('This is a local dev mock. Form submissions are disabled.'); return false;">
          
          <div style="margin-bottom: 1.5rem;">
            <label for="firstname" style="font-weight: 600; display: block; margin-bottom: .5rem;">First Name *</label>
            <input type="text" id="firstname" value="{{ user.firstname | escape }}" required style="width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px;" />
          </div>
          
          <div style="margin-bottom: 1.5rem;">
            <label for="lastname" style="font-weight: 600; display: block; margin-bottom: .5rem;">Last Name *</label>
            <input type="text" id="lastname" value="{{ user.lastname | escape }}" required style="width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px;" />
          </div>

          <div style="margin-bottom: 1.5rem;">
            <label for="emailaddress1" style="font-weight: 600; display: block; margin-bottom: .5rem;">Email *</label>
            <input type="email" id="emailaddress1" value="{{ user.emailaddress1 | escape }}" required style="width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px;" />
          </div>

          <div style="margin-bottom: 1.5rem;">
            <label for="telephone1" style="font-weight: 600; display: block; margin-bottom: .5rem;">Business Phone</label>
            <input type="text" id="telephone1" value="{{ user.telephone1 | escape }}" style="width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px;" />
          </div>

          <div style="margin-bottom: 1.5rem;">
            <label for="organizationname" style="font-weight: 600; display: block; margin-bottom: .5rem;">Organization Name</label>
            <input type="text" id="organizationname" value="{{ user.adx_organizationname | escape }}" style="width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px;" />
          </div>

          <div style="margin-bottom: 1.5rem;">
            <label for="title" style="font-weight: 600; display: block; margin-bottom: .5rem;">Title</label>
            <input type="text" id="title" value="{{ user.jobtitle | escape }}" style="width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px;" />
          </div>

          <div style="margin-bottom: 1.5rem;">
            <label for="marketingonly" style="font-weight: 600; display: flex; align-items: center; gap: 8px;">
              <input type="checkbox" id="marketingonly" />
              I would like to receive marketing communications
            </label>
          </div>
          
          <button type="submit" style="padding: 10px 20px; background-color: #005A9C; color: white; border: none; border-radius: 4px; font-weight: bold; cursor: pointer;">
            Update
          </button>
        </form>

        <div style="margin-top: 2rem; padding: 1rem; background-color: #f8f9fa; border-left: 4px solid #17a2b8;">
          <strong>Local Dev Note:</strong> This is a built-in platform page (<code>~/Pages/Profile.aspx</code>). 
          The form above is a local mock provided by <code>powerpages-local</code>. Server-side ASP.NET components are not rendered locally.
        </div>
      </div>
    </div>
  </div>
</div>
  `
};
