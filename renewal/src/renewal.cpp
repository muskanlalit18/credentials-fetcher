#include "daemon.h"
#include "util.hpp"
#include <chrono>
#include <filesystem>
#include <stdlib.h>

int krb_ticket_renew_handler( Daemon cf_daemon )
{
    std::string krb_files_dir = cf_daemon.krb_files_dir;
    int interval = cf_daemon.krb_ticket_handle_interval;
    CF_logger cf_logger = cf_daemon.cf_logger;

    if ( krb_files_dir.empty() )
    {
        fprintf( stderr, SD_CRIT "directory path for kerberos tickets is not provided" );
        return -1;
    }

    while ( !cf_daemon.got_systemd_shutdown_signal )
    {
        try
        {
            auto x = std::chrono::steady_clock::now() + std::chrono::minutes( interval );
            std::this_thread::sleep_until( x );
            std::cout << Util::getCurrentTime() << '\t' << "INFO: renewal started" << std::endl;

            // identify the metadata files in the krb directory
            std::vector<std::string> metadatafiles;
            for ( std::filesystem::recursive_directory_iterator end, dir( krb_files_dir );
                  dir != end; ++dir )
            {
                auto path = dir->path();
                if ( std::filesystem::is_regular_file( path ) )
                {
                    // find the file with metadata extension
                    std::string filename = path.filename().string();
                    if ( !filename.empty() && filename.find( "_metadata" ) != std::string::npos )
                    {
                        std::string filepath = path.parent_path().string() + "/" + filename;
                        metadatafiles.push_back( filepath );
                    }
                }
            }

            // read the information of service account from the files
            for ( auto file_path : metadatafiles )
            {
                std::list<krb_ticket_info_t*> krb_ticket_info_list =
                    read_meta_data_json( file_path );
                std::string log_message;

                // refresh the kerberos tickets for the service accounts, if tickets ready for
                // renewal
                for ( auto krb_ticket : krb_ticket_info_list )
                {
                    std::pair<int, std::string> gmsa_ticket_result;
                    std::string krb_cc_name = krb_ticket->krb_file_path;
                    std::string domainless_user = krb_ticket->domainless_user;
                    // check if the ticket is ready for renewal and not created in domainless mode
                    if ( ( domainless_user.empty() ||
                           domainless_user.find( "awsdomainlessusersecret" ) !=
                               std::string::npos ) &&
                         is_ticket_ready_for_renewal( krb_ticket, cf_daemon.cf_logger ) )
                    {
                        int num_retries = 1;
                        for ( int i = 0; i <= num_retries; i++ )
                        {
                            gmsa_ticket_result = fetch_gmsa_password_and_create_krb_ticket(
                                krb_ticket->domain_name, krb_ticket, krb_cc_name, cf_logger );
                            if ( gmsa_ticket_result.first != 0 )
                            {
                                std::pair<int, std::string> status;
                                log_message = "ERROR: Cannot get gMSA krb ticket using account " +
                                              krb_ticket->service_account_name;
                                cf_logger.logger( LOG_ERR, log_message.c_str() );
                                if ( domainless_user.find( "awsdomainlessusersecret" ) !=
                                     std::string::npos )
                                {
                                    int pos = domainless_user.find( ":" );
                                    std::string domainlessUser = domainless_user.substr( pos + 1 );
                                    status = Util::generate_krb_ticket_using_secret_vault(
                                        krb_ticket->domain_name, domainlessUser, cf_logger );
                                }
                                else
                                {
                                    status = generate_krb_ticket_from_machine_keytab(
                                        krb_ticket->domain_name, cf_logger );
                                }
                                if ( status.first < 0 )
                                {
                                    log_message = "Error " + std::to_string( status.first ) +
                                                  ": Cannot get machine krb ticket";
                                    cf_logger.logger( LOG_ERR, log_message.c_str() );
                                }
                                else
                                {
                                    break;
                                }
                            }
                        }
                    }
                    // else
                    // {
                    //     log_message = "gMSA ticket is at " + krb_cc_name;
                    //     cf_logger.logger( LOG_INFO, log_message.c_str() );
                    // }
                }
            }
        }
        catch ( const std::exception& ex )
        {
            std::string log_str = Util::getCurrentTime() + '\t' + "ERROR: '" + ex.what() + "'!\n";
            cf_logger.logger( LOG_ERR, log_str.c_str() );
            std::cerr << log_str << std::endl;
            log_str = Util::getCurrentTime() + '\t' + "ERROR: failed to run ticket renewal";
            std::cerr << log_str << std::endl;
            cf_logger.logger( LOG_ERR, log_str.c_str() );
            break;
        }
    }
    return -1;
}
