import{defineConfig}from'@playwright/test';
export default defineConfig({testDir:'tests/browser',timeout:60000,use:{baseURL:'http://127.0.0.1:5181',viewport:{width:1440,height:1100},screenshot:'only-on-failure'},reporter:'list'});
