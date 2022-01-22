#ifndef ELF_H
#define ELF_H

#include <cstdint>

class ELFSECTION {
public:
        uint32_t m_start;
        uint32_t m_len;
        char     m_data[4];
};

bool			isELF     (const char *filename);
void			elfread   (const char *filename, ELFSECTION **&sections);
uint32_t	getSymbol (const char *filename, const char *symbolName);

#endif
