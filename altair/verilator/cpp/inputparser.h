#ifndef INPUTPARSER_H
#define INPUTPARSER_H

#include <algorithm>

//  from https://stackoverflow.com/questions/865668/how-to-parse-command-line-arguments-in-c
//  author: iain
class INPUTPARSER {
public:
        INPUTPARSER(int &argc, char **argv) {
                for (int ii = 0; ii < argc; ii++)
                        m_tokens.push_back(std::string(argv[ii]));
        }
        const std::string &GetCmdOption(const std::string &option) const {
                std::vector<std::string>::const_iterator itr;
                itr = std::find(m_tokens.begin(), m_tokens.end(), option);
                if (itr != m_tokens.end() && ++itr != m_tokens.end())
                        return *itr;
                static const std::string empty("");
                return empty;
        }
        bool CmdOptionExist(const std::string &option) const {
                return std::find(m_tokens.begin(), m_tokens.end(), option) != m_tokens.end();
        }
private:
        std::vector<std::string> m_tokens;
};

#endif
