#include "fingerprint.h"
#include <wincrypt.h>
#include <stdio.h>
#include <string.h>
#include "contract_types.h"
#include "contract.inc"
int ig_hash_file(const WCHAR *path, char hash[65])
{
    HANDLE f = INVALID_HANDLE_VALUE;
    HCRYPTPROV provider = 0;
    HCRYPTHASH state = 0;
    BYTE bytes[65536], digest[32];
    DWORD got, n = sizeof(digest), total = 0;
    unsigned i;
    int ok = 0;
    hash[0] = 0;
    f = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (f == INVALID_HANDLE_VALUE) goto done;
    if (!CryptAcquireContextW(&provider,NULL,NULL,PROV_RSA_AES,CRYPT_VERIFYCONTEXT) ||
        !CryptCreateHash(provider,CALG_SHA_256,0,0,&state)) goto done;
    for (;;) {
        if (!ReadFile(f,bytes,sizeof(bytes),&got,NULL)) goto done;
        if (!got) break;
        total += got;
        if (!CryptHashData(state,bytes,got,0)) goto done;
    }
    if (!total || !CryptGetHashParam(state,HP_HASHVAL,digest,&n,0) || n != 32) goto done;
    for (i=0;i<32;++i) sprintf(hash+i*2,"%02x",digest[i]);
    ok = 1;
done:
    if (state) CryptDestroyHash(state);
    if (provider) CryptReleaseContext(provider,0);
    if (f != INVALID_HANDLE_VALUE) CloseHandle(f);
    return ok;
}
int ig_check_file(const WCHAR *path, char hash[65], char *error, unsigned cap)
{
    HANDLE f;
    BYTE header[4096];
    DWORD got = 0;
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER *)header;
    IMAGE_NT_HEADERS32 *nt;
    int ok = 0;
    hash[0] = 0;
    if (cap) error[0] = 0;
    f = CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
    if (f == INVALID_HANDLE_VALUE) goto done;
    if (!ReadFile(f,header,sizeof(header),&got,NULL) || got < sizeof(IMAGE_DOS_HEADER) || dos->e_magic != IMAGE_DOS_SIGNATURE ||
        dos->e_lfanew < 0 || (DWORD)dos->e_lfanew > got || sizeof(IMAGE_NT_HEADERS32) > got-(DWORD)dos->e_lfanew) {
        CloseHandle(f); goto done;
    }
    nt = (IMAGE_NT_HEADERS32 *)(header+(DWORD)dos->e_lfanew);
    ok = nt->Signature == IMAGE_NT_SIGNATURE && nt->FileHeader.Machine == IMAGE_FILE_MACHINE_I386 &&
        nt->OptionalHeader.Magic == IMAGE_NT_OPTIONAL_HDR32_MAGIC && nt->OptionalHeader.ImageBase == IG_IMAGE_BASE &&
        nt->OptionalHeader.SizeOfImage == IG_IMAGE_SIZE && nt->FileHeader.TimeDateStamp == IG_TIMESTAMP;
    CloseHandle(f);
    if (ok) ok = ig_hash_file(path,hash) && !strcmp(hash,IG_SHA256);
done:
    if (!ok && cap) _snprintf_s(error,cap,_TRUNCATE,"PE32/x86 header or stock SHA-256 mismatch (Win32=%lu)",GetLastError());
    return ok;
}
