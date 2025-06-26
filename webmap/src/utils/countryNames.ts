// Country name lookup utility using REST Countries API
// Caches results to avoid repeated API calls

interface CountryData {
  name: {
    common: string;
    official: string;
  };
}

// Cache to store country names to avoid repeated API calls
const countryNameCache: { [iso: string]: string } = {};

// Batch cache to store multiple lookups
let pendingLookups: Set<string> = new Set();
let lookupPromise: Promise<void> | null = null;

/**
 * Get country name from ISO code using REST Countries API
 * Uses caching to minimize API calls
 */
export const getCountryName = async (isoCode: string): Promise<string> => {
  if (!isoCode) return isoCode;
  
  // Return cached result if available
  if (countryNameCache[isoCode]) {
    return countryNameCache[isoCode];
  }
  
  // Add to pending lookups
  pendingLookups.add(isoCode);
  
  // If there's no ongoing batch lookup, start one
  if (!lookupPromise) {
    lookupPromise = batchLookupCountries();
  }
  
  await lookupPromise;
  
  // Return the cached result or fallback to ISO code
  return countryNameCache[isoCode] || isoCode;
};

/**
 * Batch lookup multiple countries at once to minimize API calls
 */
const batchLookupCountries = async (): Promise<void> => {
  const isoCodes = Array.from(pendingLookups);
  pendingLookups.clear();
  lookupPromise = null;
  
  if (isoCodes.length === 0) return;
  
  // Small delay to allow batching more requests
  await new Promise(resolve => setTimeout(resolve, 50));
  
  try {
    // Lookup countries individually (REST Countries doesn't support batch by alpha codes)
    const promises = isoCodes.map(async (isoCode) => {
      try {
        const response = await fetch(`https://restcountries.com/v3.1/alpha/${isoCode}`);
        if (response.ok) {
          const data: CountryData[] = await response.json();
          if (data && data.length > 0 && data[0].name?.common) {
            countryNameCache[isoCode] = data[0].name.common;
          } else {
            countryNameCache[isoCode] = isoCode; // Fallback to ISO code
          }
        } else {
          countryNameCache[isoCode] = isoCode; // Fallback to ISO code
        }
      } catch (error) {
        console.warn(`Failed to fetch country name for ${isoCode}:`, error);
        countryNameCache[isoCode] = isoCode; // Fallback to ISO code
      }
    });
    
    await Promise.all(promises);
  } catch (error) {
    console.error('Batch country lookup failed:', error);
    // Set fallbacks for all failed lookups
    isoCodes.forEach(isoCode => {
      if (!countryNameCache[isoCode]) {
        countryNameCache[isoCode] = isoCode;
      }
    });
  }
};

/**
 * Preload country names for a list of ISO codes
 * Useful for preloading data when component mounts
 */
export const preloadCountryNames = async (isoCodes: string[]): Promise<void> => {
  const uncachedCodes = isoCodes.filter(iso => iso && !countryNameCache[iso]);
  if (uncachedCodes.length === 0) return;
  
  uncachedCodes.forEach(iso => pendingLookups.add(iso));
  
  if (!lookupPromise) {
    lookupPromise = batchLookupCountries();
  }
  
  await lookupPromise;
};

/**
 * Get cached country name (synchronous)
 * Returns ISO code if not cached
 */
export const getCachedCountryName = (isoCode: string): string => {
  return countryNameCache[isoCode] || isoCode;
};

/**
 * Clear the country name cache
 */
export const clearCountryNameCache = (): void => {
  Object.keys(countryNameCache).forEach(key => delete countryNameCache[key]);
}; 