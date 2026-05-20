'use strict';
/**
 * Region enforcement — rejects cross-region tenant requests.
 * Only active when DEPLOYMENT_REGION env var is set ('eu' | 'us').
 * Returns HTTP 451 with redirect_to so the client can retry the correct endpoint.
 */
const fs = require('fs');
const path = require('path');

const DEPLOYMENT_REGION = process.env.DEPLOYMENT_REGION;

const REGION_ENDPOINTS = {
  eu: process.env.REGION_EU_ENDPOINT || 'https://eu.api.aeternus.ai',
  us: process.env.REGION_US_ENDPOINT || 'https://us.api.aeternus.ai',
};

const REGIONS_FILE = path.join(
  process.env.AI_EMPLOYEE_HOME || process.env.HOME || '/tmp',
  '.ai-employee', 'state', 'tenant_regions.json'
);

function loadRegionMap() {
  try { return JSON.parse(fs.readFileSync(REGIONS_FILE, 'utf8')); }
  catch { return {}; }
}

function getTenantRegion(tenantId) {
  if (!tenantId) return null;
  return loadRegionMap()[tenantId] || null;
}

function enforceRegion(req, res, next) {
  if (!DEPLOYMENT_REGION) return next();
  const tenantId = req.user?.tenant_id || req.jwtPayload?.tenant_id || req.tenant?.tenant_id;
  if (!tenantId) return next();
  const tenantRegion = getTenantRegion(tenantId);
  if (tenantRegion && tenantRegion !== DEPLOYMENT_REGION) {
    return res.status(451).json({
      error: 'data_residency_violation',
      message: `Tenant '${tenantId}' data is hosted in region '${tenantRegion}'. Please use the correct regional endpoint.`,
      redirect_to: REGION_ENDPOINTS[tenantRegion] || null,
    });
  }
  next();
}

module.exports = { enforceRegion, getTenantRegion, DEPLOYMENT_REGION };
