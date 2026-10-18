import{test,expect}from'@playwright/test';
test('real benchmark, customer filters, details and export',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('/');
 await expect(page.getByRole('heading',{name:'See the customer. Understand the pattern.'})).toBeVisible();
 await expect(page.getByText('1,907',{exact:true}).first()).toBeVisible();
 await page.screenshot({path:'docs/customerlens-overview.png',fullPage:true});
 await page.getByRole('button',{name:'Customer explorer',exact:true}).click();
 await expect(page.locator('tbody tr')).toHaveCount(15);
 await page.getByLabel('Customer segment').selectOption('Cooling');
 await expect(page.locator('tbody tr .customer-tag').first()).toHaveText('Cooling');
 await page.getByRole('button',{name:/Inspect CL-/}).first().click();
 await expect(page.getByRole('dialog')).toBeVisible();await expect(page.getByText('Later observed outcome',{exact:true})).not.toBeVisible();
 await page.getByRole('button',{name:'Reveal historical outcome'}).click();await expect(page.getByText('Later observed outcome',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Close customer details'}).click();
 const exporting=page.waitForEvent('download');await page.getByRole('button',{name:'Export audience',exact:true}).click();expect((await exporting).suggestedFilename()).toBe('customerlens-audience.csv');
 await page.getByRole('button',{name:'Reset filters'}).click();await page.getByRole('button',{name:'Next customers'}).click();await expect(page.getByText(/Showing 16/)).toBeVisible();
 await page.getByLabel('Search customer ID').fill('not-a-customer');await expect(page.getByText(/No customers match/)).toBeVisible();
 expect(errors).toEqual([]);
});
test('cohorts and model diagnostics expose limitations',async({page})=>{
 await page.goto('/');await page.getByRole('button',{name:'Cohort retention',exact:true}).click();await expect(page.getByRole('heading',{name:'Monthly customer retention'})).toBeVisible();
 await expect(page.locator('.unobserved').first()).toBeVisible();await page.screenshot({path:'docs/customerlens-cohorts.png',fullPage:true});
 await page.getByRole('button',{name:'Model lab',exact:true}).click();await expect(page.getByRole('heading',{name:'Purchase-propensity benchmark'})).toBeVisible();
 await page.getByLabel('Repeat-purchase model').selectOption('prevalence');await expect(page.getByText('0.224',{exact:true}).first()).toBeVisible();
 await page.getByRole('button',{name:'Data & methods',exact:true}).click();await expect(page.getByRole('heading',{name:'Cleaning and population audit'})).toBeVisible();
});
test('mobile overview and explorer do not overflow',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.goto('/');await expect(page.getByRole('heading',{name:'See the customer. Understand the pattern.'})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
 await page.getByRole('button',{name:'Customer explorer',exact:true}).click();await expect(page.getByLabel('Customer segment')).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();await page.screenshot({path:'docs/customerlens-mobile.png',fullPage:true});
});
