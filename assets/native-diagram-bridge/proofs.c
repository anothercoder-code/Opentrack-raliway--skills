#include <windows.h>
#include <wincrypt.h>
#include <stdio.h>
#include <wchar.h>
#include <string.h>
#include "contract.h"

int verify_sha256(const wchar_t *path, const char *expected)
{
    HCRYPTPROV provider = 0; HCRYPTHASH hash = 0;
    HANDLE file = INVALID_HANDLE_VALUE; BYTE buffer[32768], digest[32];
    char hex[65]; DWORD n, size = sizeof(digest); int ok = 0; unsigned i;
    file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) goto done;
    if (!CryptAcquireContextW(&provider, NULL, NULL, PROV_RSA_AES, CRYPT_VERIFYCONTEXT) ||
        !CryptCreateHash(provider, CALG_SHA_256, 0, 0, &hash)) goto done;
    for (;;) {
        if (!ReadFile(file, buffer, sizeof(buffer), &n, NULL)) goto done;
        if (!n) break;
        if (!CryptHashData(hash, buffer, n, 0)) goto done;
    }
    if (!CryptGetHashParam(hash, HP_HASHVAL, digest, &size, 0) || size != 32) goto done;
    for (i = 0; i < 32; ++i) sprintf_s(hex + 2 * i, 3, "%02x", digest[i]);
    ok = !_stricmp(hex, expected);
done:
    if (hash) CryptDestroyHash(hash);
    if (provider) CryptReleaseContext(provider, 0);
    if (file != INVALID_HANDLE_VALUE) CloseHandle(file);
    return ok;
}

 

int verify_software_authorization(void)
{
    if (AUTHORIZATION_EXPIRES_UNIX != 0ULL) {
        FILETIME value; ULARGE_INTEGER ticks; unsigned long long seconds;
        GetSystemTimeAsFileTime(&value);
        ticks.LowPart=value.dwLowDateTime; ticks.HighPart=value.dwHighDateTime;
        seconds=ticks.QuadPart/10000000ULL;
        if(seconds<11644473600ULL ||
           seconds-11644473600ULL>=AUTHORIZATION_EXPIRES_UNIX) return 0;
    }
    return verify_sha256(AUTHORIZATION_RECORD_W,AUTHORIZATION_RECORD_SHA);
}
