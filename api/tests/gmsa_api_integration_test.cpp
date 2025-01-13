#include "daemon.h"

#include <aws/core/Aws.h>
#include <aws/core/utils/StringUtils.h>
#include <aws/core/utils/memory/stl/AWSString.h>
#include <aws/s3/S3Client.h>
#include <aws/s3/model/GetObjectRequest.h>
#include <credentialsfetcher.grpc.pb.h>
#include <grpc++/grpc++.h>
#include <gtest/gtest.h>
#include <json/json.h>
#include <utility>

#define unix_socket_address "unix:/var/credentials-fetcher/socket/credentials_fetcher.sock"

#define CF_TEST_STANDARD_USERNAME "CF_TEST_STANDARD_USERNAME"
#define CF_TEST_STANDARD_USER_PASSWORD "CF_TEST_STANDARD_USER_PASSWORD"
#define CF_TEST_DOMAIN "CF_TEST_DOMAIN"
#define CF_TEST_CREDSPEC_ARN "CF_TEST_CREDSPEC_ARN"

#define AWS_ACCESS_KEY_ID "AWS_ACCESS_KEY_ID"
#define AWS_SECRET_ACCESS_KEY "AWS_SECRET_ACCESS_KEY"
#define AWS_SESSION_TOKEN "AWS_SESSION_TOKEN"
#define AWS_REGION "AWS_REGION"

static std::string get_environment_var( const char* varname )
{
    const char* value = std::getenv( varname );
    if ( !value )
    {
        throw std::runtime_error( std::string( "Environment variable not set: " ) + varname );
    }
    return std::string( value );
}

class GmsaIntegrationTest : public ::testing::Test
{
  public:
    static std::string cred_spec_contents;

  protected:
    std::unique_ptr<credentialsfetcher::CredentialsFetcherService::Stub> _stub;
    static std::string
        arn_lease_id_; // Static member to share between AddKerberosArnLeaseMethod_Test and
                       // RenewKerberosArnLeaseMethod_Test
    static std::string
        non_domain_joined_lease_id_; // Static member to share between
                                     // AddNonDomainJoinedKerberosLeaseMethod_Test and
                                     // RenewNonDomainJoinedKerberosLeaseMethod_Test

    void SetUp() override
    {
        auto channel =
            grpc::CreateChannel( unix_socket_address, grpc::InsecureChannelCredentials() );
        _stub = credentialsfetcher::CredentialsFetcherService::NewStub( channel );
    }
};

std::string GmsaIntegrationTest::arn_lease_id_;
std::string GmsaIntegrationTest::non_domain_joined_lease_id_;
std::string GmsaIntegrationTest::cred_spec_contents;

TEST_F( GmsaIntegrationTest, HealthCheck_Test )
{
    // Prepare request
    credentialsfetcher::HealthCheckRequest request;
    request.set_service( "cfservice" );

    // Call the API
    credentialsfetcher::HealthCheckResponse response;
    grpc::ClientContext context;
    grpc::Status status = _stub->HealthCheck( &context, request, &response );

    // Verify response
    ASSERT_TRUE( status.ok() ) << status.error_message();
    ASSERT_EQ( response.status(), "OK" ) << "Health check should return OK";
}

TEST_F( GmsaIntegrationTest, A_AddNonDomainJoinedKerberosLeaseMethod_Test )
{
    // Prepare request
    credentialsfetcher::CreateNonDomainJoinedKerberosLeaseRequest request;

    // Set test credentials
    request.set_username( get_environment_var( CF_TEST_STANDARD_USERNAME ) );
    request.set_password( get_environment_var( CF_TEST_STANDARD_USER_PASSWORD ) );
    request.set_domain( get_environment_var( CF_TEST_DOMAIN ) );

    // Add test credspec content
    request.add_credspec_contents( cred_spec_contents );

    credentialsfetcher::CreateNonDomainJoinedKerberosLeaseResponse response;
    grpc::ClientContext context;

    // Call the API
    grpc::Status status = _stub->AddNonDomainJoinedKerberosLease( &context, request, &response );
    non_domain_joined_lease_id_ = response.lease_id();

    // Verify response
    ASSERT_TRUE( status.ok() ) << status.error_message();
    ASSERT_FALSE( response.lease_id().empty() ) << "Lease ID should not be empty";
    ASSERT_GT( response.created_kerberos_file_paths_size(), 0 )
        << "Should have created at least one kerberos file";

    // Verify file paths exist
    for ( int i = 0; i < response.created_kerberos_file_paths_size(); i++ )
    {
        const std::string& file_path = response.created_kerberos_file_paths( i ) + "/krb5cc";
        ASSERT_TRUE( std::filesystem::exists( file_path ) )
            << "Kerberos file " << file_path << " should exist";
    }
}

TEST_F( GmsaIntegrationTest, B_RenewNonDomainJoinedKerberosLeaseMethod_Test )
{
    if ( non_domain_joined_lease_id_.empty() )
    {
        GTEST_SKIP() << "Skipping test because AddNonDomainJoinedKerberosLease_Test failed";
    }

    // Prepare request
    credentialsfetcher::RenewNonDomainJoinedKerberosLeaseRequest request;

    // Set test credentials
    request.set_username( get_environment_var( CF_TEST_STANDARD_USERNAME ) );
    request.set_password( get_environment_var( CF_TEST_STANDARD_USER_PASSWORD ) );
    request.set_domain( get_environment_var( CF_TEST_DOMAIN ) );

    credentialsfetcher::RenewNonDomainJoinedKerberosLeaseResponse response;
    grpc::ClientContext context;

    // Call the API
    grpc::Status status = _stub->RenewNonDomainJoinedKerberosLease( &context, request, &response );

    // Verify response
    ASSERT_TRUE( status.ok() ) << status.error_message();
}

TEST_F( GmsaIntegrationTest, C_DeleteKerberosLeaseMethod_Test )
{
    if ( non_domain_joined_lease_id_.empty() )
    {
        GTEST_SKIP() << "Skipping test because AddNonDomainJoinedKerberosLease_Test failed";
    }

    // Prepare request
    credentialsfetcher::DeleteKerberosLeaseRequest request;

    // Set test credentials
    request.set_lease_id( non_domain_joined_lease_id_ );

    credentialsfetcher::DeleteKerberosLeaseResponse response;
    grpc::ClientContext context;

    // Call the API
    grpc::Status status = _stub->DeleteKerberosLease( &context, request, &response );

    // Verify response
    ASSERT_TRUE( status.ok() ) << status.error_message();
    ASSERT_FALSE( response.lease_id().empty() ) << "Lease ID should not be empty";
    ASSERT_GT( response.deleted_kerberos_file_paths_size(), 0 )
        << "Should have deleted at least one kerberos file";

    // Verify file paths doesn't exist
    for ( int i = 0; i < response.deleted_kerberos_file_paths_size(); i++ )
    {
        const std::string& file_path = response.deleted_kerberos_file_paths( i );
        ASSERT_TRUE( !std::filesystem::exists( file_path ) )
            << "Kerberos file " << file_path << " shouldn't exist";
    }
}

TEST_F( GmsaIntegrationTest, A_AddKerberosArnLeaseMethod_Test )
{
    // Prepare request
    credentialsfetcher::KerberosArnLeaseRequest request;

    std::string arn = get_environment_var( "CREDSPEC_ARN" );
    arn += "#123/WebApp01";
    request.add_credspec_arns( arn );
    request.set_access_key_id( get_environment_var( AWS_ACCESS_KEY_ID ) );
    request.set_secret_access_key( get_environment_var( AWS_SECRET_ACCESS_KEY ) );
    request.set_session_token( get_environment_var( AWS_SESSION_TOKEN ) );
    request.set_region( get_environment_var( AWS_REGION ) );

    credentialsfetcher::CreateKerberosArnLeaseResponse response;
    grpc::ClientContext context;

    // Call the API
    grpc::Status status = _stub->AddKerberosArnLease( &context, request, &response );

    arn_lease_id_ = response.lease_id();

    // Verify response
    ASSERT_TRUE( status.ok() ) << status.error_message();
    ASSERT_FALSE( response.lease_id().empty() ) << "Lease ID should not be empty";
    ASSERT_GT( response.krb_ticket_response_map_size(), 0 )
        << "Should have created at least one kerberos file";

    // Verify file paths exist
    for ( int i = 0; i < response.krb_ticket_response_map_size(); i++ )
    {
        const std::string& file_path =
            response.krb_ticket_response_map( i ).created_kerberos_file_paths() + "/krb5cc";
        ASSERT_TRUE( std::filesystem::exists( file_path ) )
            << "Kerberos file " << file_path << " should exist";
    }
}

TEST_F( GmsaIntegrationTest, B_RenewKerberosArnLeaseMethod_Test )
{
    if ( arn_lease_id_.empty() )
    {
        GTEST_SKIP() << "Skipping test because AddKerberosArnLeaseMethod_Test failed";
    }

    // Prepare request
    credentialsfetcher::RenewKerberosArnLeaseRequest request;

    request.set_access_key_id( get_environment_var( AWS_ACCESS_KEY_ID ) );
    request.set_secret_access_key( get_environment_var( AWS_SECRET_ACCESS_KEY ) );
    request.set_session_token( get_environment_var( AWS_SESSION_TOKEN ) );
    request.set_region( get_environment_var( AWS_REGION ) );

    credentialsfetcher::RenewKerberosArnLeaseResponse response;
    grpc::ClientContext context;

    // Call the API
    grpc::Status status = _stub->RenewKerberosArnLease( &context, request, &response );

    // Verify response
    ASSERT_TRUE( status.ok() ) << status.error_message();
}

struct S3Location
{
    Aws::String bucket;
    Aws::String key;
};

S3Location parseS3Arn( const Aws::String& arnString )
{
    // Split ARN into components
    Aws::Vector<Aws::String> arnParts = Aws::Utils::StringUtils::Split( arnString, ':' );

    // Get the bucket and key part (last component)
    Aws::String resourcePart = arnParts[3];

    // Split resource into bucket and key if there's a '/'
    size_t delimiterPos = resourcePart.find( '/' );
    return S3Location{ resourcePart.substr( 0, delimiterPos ),
                       resourcePart.substr( delimiterPos + 1 ) };
}

void get_cred_spec_contents()
{
    auto location = parseS3Arn( get_environment_var( CF_TEST_CREDSPEC_ARN ) );
    Aws::String bucket = location.bucket;
    Aws::String key = location.key;

    Aws::SDKOptions options;
    Aws::InitAPI( options );
    {
        // Create S3 client
        Aws::Client::ClientConfiguration clientConfig;
        clientConfig.region = get_environment_var( AWS_REGION );
        Aws::S3::S3Client s3_client( clientConfig );

        // Configure S3 request
        Aws::S3::Model::GetObjectRequest request;
        request.SetBucket( bucket );
        request.SetKey( key );

        // Get the object
        auto outcome = s3_client.GetObject( request );

        if ( outcome.IsSuccess() )
        {
            // Read the JSON data
            std::stringstream json_data;
            json_data << outcome.GetResult().GetBody().rdbuf();
            json_data.seekg( 0 );
            // Parse JSON
            Json::Value root;
            Json::CharReaderBuilder reader;
            Json::StreamWriterBuilder builder;
            builder["indentation"] = ""; // for single line output
            std::string errors;
            if ( !Json::parseFromStream( reader, json_data, &root, &errors ) )
            {
                throw std::runtime_error( "Failed to parse JSON: " + errors );
            }
            if ( root.empty() )
            {
                throw std::runtime_error( "Parsed JSON is empty" );
            }
            // Assign values to test constants
            std::string jsonString = Json::writeString( builder, root );
            if ( jsonString.empty() )
            {
                throw std::runtime_error( "Failed to serialize JSON to string" );
            }
            GmsaIntegrationTest::cred_spec_contents = jsonString;
        }
        else
        {
            throw std::runtime_error( "Error accessing S3: " + outcome.GetError().GetMessage() );
        }
    }
}

int main( int argc, char** argv )
{
    get_cred_spec_contents();

    testing::InitGoogleTest( &argc, argv );
    return RUN_ALL_TESTS();
}
