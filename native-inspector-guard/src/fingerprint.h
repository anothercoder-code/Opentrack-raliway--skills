#ifndef IG_FINGERPRINT_H
#define IG_FINGERPRINT_H
#include <windows.h>
int ig_check_file(const WCHAR *path, char hash[65], char *error, unsigned cap);
int ig_hash_file(const WCHAR *path, char hash[65]);
#endif
